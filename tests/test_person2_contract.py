"""Person 2 contract verification. Simulates Person 1 and Person 3 interfaces."""

from types import SimpleNamespace
import pytest
from stores.graph_store import GraphStore


class FakeVectorStoreAttrs:
    def __init__(self, results):
        self.results = results

    def query(self, query_text, top_k=5):
        return [SimpleNamespace(node_id=nid, score=s) for nid, s in self.results[:top_k]]


class FakeVectorStoreDicts:
    def __init__(self, results):
        self.results = results

    def query(self, query_text, top_k=5):
        return [{"node_id": nid, "score": s} for nid, s in self.results[:top_k]]


class FakeVectorStoreMalformed:
    def __init__(self, results):
        self.results = results

    def query(self, query_text, top_k=5):
        return ["not-a-match", "also-not-a-match"]


class FakeAuditChain:
    def __init__(self):
        self.entries = []

    def append(self, operation, node_id, details):
        self.entries.append((operation, node_id, details))


class NoAppendObject:
    pass


@pytest.fixture
def tmp_store(tmp_path):
    def _make(vector_store=None, audit_chain=None):
        return GraphStore(
            path=str(tmp_path / "kg.json"),
            vector_store=vector_store,
            audit_chain=audit_chain,
        )

    return _make


def test_commit_session_returns_correct_shape(tmp_store):
    store = tmp_store()
    store.add_entity({
        "node_id": "u",
        "content": "user",
        "entity_type": "user",
        "deletion_state": "active",
        "session_id": "sess_001",
    })
    result = store.on_session_commit("sess_001")
    for key in ("session_id", "orphans_found", "healed_count", "quarantined"):
        assert key in result
    assert result["session_id"] == "sess_001"


def test_commit_session_calls_heal_orphans(tmp_store):
    store = tmp_store()
    store.add_entity({
        "node_id": "u",
        "content": "orphan user",
        "entity_type": "user",
        "deletion_state": "active",
        "session_id": "sess_001",
    })
    result = store.on_session_commit("sess_001")
    assert result["orphans_found"] >= 1
    assert result["healed_count"] + len(result.get("quarantined", [])) >= 1


def test_vector_store_attribute_shape(tmp_store):
    store = tmp_store(vector_store=FakeVectorStoreAttrs([("target", 0.95)]))
    store.add_entity({
        "node_id": "orphan",
        "content": "python language preference",
        "entity_type": "preference",
        "deletion_state": "active",
    })
    store.add_entity({
        "node_id": "target",
        "content": "python language preference",
        "entity_type": "preference",
        "deletion_state": "active",
    })
    store.on_session_commit("")
    assert "target" in [n["node_id"] for n in store.get_neighbors("orphan")]


def test_vector_store_dict_shape(tmp_store):
    store = tmp_store(vector_store=FakeVectorStoreDicts([("target", 0.95)]))
    store.add_entity({
        "node_id": "orphan",
        "content": "python language preference",
        "entity_type": "preference",
        "deletion_state": "active",
    })
    store.add_entity({
        "node_id": "target",
        "content": "python language preference",
        "entity_type": "preference",
        "deletion_state": "active",
    })
    store.on_session_commit("")
    assert "target" in [n["node_id"] for n in store.get_neighbors("orphan")]


def test_vector_store_malformed_falls_back(tmp_store):
    store = tmp_store(vector_store=FakeVectorStoreMalformed([]))
    store.add_entity({
        "node_id": "orphan",
        "content": "python preference",
        "entity_type": "preference",
        "deletion_state": "active",
    })
    result = store.on_session_commit("")
    assert isinstance(result, dict)


def test_audit_chain_called(tmp_store):
    fake_audit = FakeAuditChain()
    store = tmp_store(audit_chain=fake_audit)
    store.add_entity({
        "node_id": "u",
        "content": "orphan",
        "entity_type": "user",
        "deletion_state": "active",
        "session_id": "s1",
    })
    store.on_session_commit("s1")
    ops = [op for op, _, _ in fake_audit.entries]
    assert any(
        op in ops
        for op in ("graph_orphan_detected", "graph_orphan_healed", "graph_orphan_quarantined")
    )


def test_audit_chain_none_does_not_crash(tmp_store):
    store = tmp_store(audit_chain=None)
    store.add_entity({
        "node_id": "u",
        "content": "orphan",
        "entity_type": "user",
        "deletion_state": "active",
        "session_id": "s1",
    })
    assert isinstance(store.on_session_commit("s1"), dict)


def test_audit_chain_missing_append_does_not_crash(tmp_store):
    store = tmp_store(audit_chain=NoAppendObject())
    store.add_entity({
        "node_id": "u",
        "content": "orphan",
        "entity_type": "user",
        "deletion_state": "active",
        "session_id": "s1",
    })
    assert isinstance(store.on_session_commit("s1"), dict)


def test_full_lifecycle_integration(tmp_path):
    path = str(tmp_path / "kg.json")
    fake_audit = FakeAuditChain()
    store = GraphStore(path=path, vector_store=None, audit_chain=fake_audit)

    store.add_entity({
        "node_id": "user",
        "content": "user entity",
        "entity_type": "user",
        "deletion_state": "active",
        "session_id": "sess_demo",
    })
    store.add_entity({
        "node_id": "python",
        "content": "prefers python",
        "entity_type": "preference",
        "deletion_state": "active",
        "session_id": "sess_demo",
    })
    store.add_entity({
        "node_id": "api_key",
        "content": "owns api key",
        "entity_type": "credential",
        "deletion_state": "active",
        "session_id": "sess_demo",
    })
    store.add_relationship("user", "python", "PREFERS")
    store.add_relationship("user", "api_key", "OWNS")

    store.kg.graph.nodes["user"]["deletion_state"] = "source_removed"
    store.kg.persist()

    result = store.on_session_commit("sess_demo")
    assert result["session_id"] == "sess_demo"

    active_ids = [e["node_id"] for e in store.get_all_active_entities()]
    assert "user" not in active_ids
    assert len(fake_audit.entries) >= 1

    reloaded = GraphStore(path=path)
    assert "user" not in [e["node_id"] for e in reloaded.get_all_active_entities()]

