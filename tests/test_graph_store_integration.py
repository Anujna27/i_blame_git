from pathlib import Path
from types import SimpleNamespace
import pytest

from stores.graph_store import GraphStore


class FakeVectorStore:
    def __init__(self, results):
        self.results = results

    def query(self, query_text, top_k=5):
        return [SimpleNamespace(node_id=nid, score=s) for nid, s in self.results[:top_k]]


def test_graph_store_persistence(tmp_path: Path):
    path = str(tmp_path / "store_test.json")
    gs = GraphStore(path=path)

    gs.add_entity({"node_id": "u1", "content": "Entity 1"})
    gs.add_entity({"node_id": "u2", "content": "Entity 2"})
    gs.add_relationship("u1", "u2", "RELATED_TO")

    gs2 = GraphStore(path=path)
    assert gs2.get_entity("u1") is not None
    assert gs2.get_entity("u2") is not None
    neighbors = gs2.get_neighbors("u1", direction="out")
    assert len(neighbors) == 1
    assert neighbors[0]["node_id"] == "u2"


def test_on_session_commit_calls_healer(tmp_path: Path):
    path = str(tmp_path / "commit_test.json")
    gs = GraphStore(path=path)

    gs.add_entity({"node_id": "iso_1", "session_id": "sess_001", "content": "Isolated 1"})
    gs.add_entity({"node_id": "iso_2", "session_id": "sess_001", "content": "Isolated 2"})
    gs.add_entity({"node_id": "iso_3", "session_id": "sess_001", "content": "Isolated 3"})

    res = gs.on_session_commit("sess_001")
    assert res["session_id"] == "sess_001"
    assert res["orphans_found"] >= 1
    assert res["healed_count"] + len(res["quarantined"]) >= 1


def test_on_session_commit_idempotent(tmp_path: Path):
    path = str(tmp_path / "idempotent_test.json")
    gs = GraphStore(path=path)

    gs.add_entity({"node_id": "idem_1", "session_id": "sess_001", "content": "Idem 1"})
    res1 = gs.on_session_commit("sess_001")
    assert res1["orphans_found"] >= 1

    res2 = gs.on_session_commit("sess_001")
    assert res2["orphans_found"] == 0 or len(res2["quarantined"]) == 0


def test_on_session_commit_survives_healer_error(tmp_path: Path, monkeypatch):
    path = str(tmp_path / "error_test.json")
    gs = GraphStore(path=path)

    def _failing_heal(*args, **kwargs):
        raise RuntimeError("Simulated healer crash")

    monkeypatch.setattr(gs.healer, "heal_orphans", _failing_heal)

    res = gs.on_session_commit("sess_crash")
    assert "error" in res
    assert "Simulated healer crash" in res["error"]
    assert res["orphans_found"] == -1


def test_get_all_active_entities_excludes_quarantined(tmp_path: Path):
    path = str(tmp_path / "quarantine_test.json")
    gs = GraphStore(path=path)

    gs.add_entity({"node_id": "q_node", "content": "Isolated to quarantine"})
    gs.heal_orphans()

    active_entities = gs.get_all_active_entities()
    assert "q_node" not in {e["node_id"] for e in active_entities}


def test_add_relationship_persists(tmp_path: Path):
    path = str(tmp_path / "rel_test.json")
    gs = GraphStore(path=path)

    gs.add_entity({"node_id": "p1", "content": "Person 1"})
    gs.add_entity({"node_id": "p2", "content": "Person 2"})
    gs.add_relationship("p1", "p2", "OWNS")

    gs_reloaded = GraphStore(path=path)
    neighbors = gs_reloaded.get_neighbors("p1", direction="out", relationship="OWNS")
    assert len(neighbors) == 1
    assert neighbors[0]["node_id"] == "p2"


def test_session_commit_with_similarity_repair(tmp_path: Path):
    path = str(tmp_path / "sim_commit.json")
    fake_vs = FakeVectorStore([("target_pref", 0.96)])
    gs = GraphStore(path=path, vector_store=fake_vs)

    gs.add_entity({"node_id": "orphan_user", "session_id": "sess_sim", "content": "Prefers Dark Mode"})
    gs.add_entity({"node_id": "target_pref", "content": "UI Settings and Themes"})

    res = gs.on_session_commit("sess_sim")
    assert res["healed_count"] >= 1

    gs_reloaded = GraphStore(path=path)
    neighbors = gs_reloaded.get_neighbors("orphan_user", direction="out")
    assert any(n["node_id"] == "target_pref" for n in neighbors)


def test_end_to_end_lifecycle(tmp_path: Path):
    """
    Simulates the full Person 2 pipeline as it will run in the demo:
    1. Create 3 entities in session sess_A
    2. Link them: user --PREFERS--> python, user --OWNS--> api_key
    3. Mark "user" entity as deleted (deletion_state="source_removed")
    4. on_session_commit("sess_A")
    5. Assert: api_key and python are now orphans (deleted_parent) and either reconnected or quarantined
    6. Assert: api_key and python never appear in get_all_active_entities() as "active" if quarantined
    7. Reload the store from disk and assert the healed/quarantined state persists
    """
    path = str(tmp_path / "demo_lifecycle.json")
    gs = GraphStore(path=path)

    # 1. Create 3 entities in session sess_A
    gs.add_entity({"node_id": "user", "session_id": "sess_A", "content": "Alice User Profile", "deletion_state": "active"})
    gs.add_entity({"node_id": "python", "session_id": "sess_A", "content": "Python 3.13 Preference", "deletion_state": "active"})
    gs.add_entity({"node_id": "api_key", "session_id": "sess_A", "content": "OpenAI API Key sk-123", "deletion_state": "active"})

    # 2. Link them: user --PREFERS--> python, user --OWNS--> api_key
    gs.add_relationship("user", "python", "PREFERS")
    gs.add_relationship("user", "api_key", "OWNS")

    # 3. Mark "user" entity as deleted (deletion_state="source_removed")
    gs.kg.graph.nodes["user"]["deletion_state"] = "source_removed"
    gs.kg.persist()

    # 4. on_session_commit("sess_A")
    commit_report = gs.on_session_commit("sess_A")

    # 5. Assert: api_key and python are now orphans (deleted_parent) and either reconnected or quarantined
    assert commit_report["orphans_found"] >= 2
    quarantined = set(commit_report["quarantined"])
    assert "api_key" in quarantined
    assert "python" in quarantined

    # 6. Assert: api_key and python never appear in get_all_active_entities() as "active" if quarantined
    active_now = {e["node_id"] for e in gs.get_all_active_entities()}
    assert "api_key" not in active_now
    assert "python" not in active_now
    assert "user" not in active_now

    # 7. Reload the store from disk and assert the healed/quarantined state persists
    gs_reloaded = GraphStore(path=path)
    active_reloaded = {e["node_id"] for e in gs_reloaded.get_all_active_entities()}
    assert "api_key" not in active_reloaded
    assert "python" not in active_reloaded
    assert gs_reloaded.get_entity("api_key")["deletion_state"] == "quarantined"
    assert gs_reloaded.get_entity("python")["deletion_state"] == "quarantined"


def test_graph_store_find_duplicates(tmp_path):
    from stores.graph_store import GraphStore
    store = GraphStore(path=str(tmp_path / "kg.json"))
    store.add_entity({"node_id": "a", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    store.add_entity({"node_id": "b", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    pairs = store.find_duplicates(threshold=0.95)
    assert len(pairs) == 1

