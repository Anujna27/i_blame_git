from pathlib import Path
from types import SimpleNamespace
import pytest

from core.graph_healer import GraphHealer
from core.knowledge_graph import KnowledgeGraph


class FakeVectorStore:
    def __init__(self, results):  # results = list of (node_id, score)
        self.results = results

    def query(self, query_text, top_k=5):
        return [SimpleNamespace(node_id=nid, score=s) for nid, s in self.results[:top_k]]


class FakeAudit:
    def __init__(self):
        self.events = []  # list of (operation, node_id, details)

    def append(self, operation, node_id, details):
        self.events.append((operation, node_id, details))


@pytest.fixture
def graph(tmp_path: Path):
    return KnowledgeGraph(path=str(tmp_path / "test_kg.json"))


@pytest.fixture
def healer(graph):
    return GraphHealer(graph=graph, vector_store=None, audit_chain=None)


def test_degree_zero_detected(graph, healer):
    graph.add_entity({"node_id": "isolated_node", "content": "Just me", "deletion_state": "active"})
    orphans = healer.find_orphans()
    assert len(orphans) == 1
    assert orphans[0].node_id == "isolated_node"
    assert orphans[0].orphan_type == "degree_zero"


def test_connected_node_not_orphan(graph, healer):
    graph.add_entity({"node_id": "n1", "content": "Node 1"})
    graph.add_entity({"node_id": "n2", "content": "Node 2"})
    graph.add_relationship("n1", "n2", "RELATED_TO")
    orphans = healer.find_orphans()
    assert len(orphans) == 0


def test_deleted_parent_orphan(graph, healer):
    graph.add_entity({"node_id": "parent", "content": "Parent node"})
    graph.add_entity({"node_id": "child", "content": "Child node", "deletion_state": "active"})
    graph.add_relationship("parent", "child", "DERIVED_FROM")

    graph.graph.nodes["parent"]["deletion_state"] = "source_removed"
    graph.persist()

    orphans = healer.find_orphans()
    child_orphans = [o for o in orphans if o.node_id == "child"]
    assert len(child_orphans) == 1
    assert child_orphans[0].orphan_type == "deleted_parent"


def test_invalid_target_detected(graph, healer):
    graph.add_entity({"node_id": "A", "content": "Entity A"})
    # Manually add edge to non-existent node B in underlying nx graph
    graph.graph.add_edge("A", "B", relationship="RELATED_TO")

    orphans = healer.find_orphans()
    invalid_targets = [o for o in orphans if o.node_id == "A"]
    assert len(invalid_targets) == 1
    assert invalid_targets[0].orphan_type == "invalid_target"


def test_orphaned_session_detected(graph, healer):
    graph.add_entity({"node_id": "s_orphan", "content": "Sess X only", "session_id": "sess_x"})
    graph.add_entity({"node_id": "s_other1", "content": "Sess Y 1", "session_id": "sess_y"})
    graph.add_entity({"node_id": "s_other2", "content": "Sess Y 2", "session_id": "sess_y"})
    graph.add_relationship("s_other1", "s_other2", "RELATED_TO")

    orphans = healer.find_orphans()
    orphan_ids = {o.node_id for o in orphans}
    assert "s_orphan" in orphan_ids
    orphan_x = [o for o in orphans if o.node_id == "s_orphan"][0]
    assert orphan_x.orphan_type == "orphaned_session"


def test_deterministic_derivation_repair(graph):
    graph.add_entity({"node_id": "parent_node", "content": "Parent Node", "deletion_state": "active"})
    graph.add_entity({
        "node_id": "child_node",
        "content": "Child Node",
        "deletion_state": "active",
        "properties": {"derivation_edges": [{"parent_id": "parent_node", "type": "DERIVED_FROM"}]},
    })

    healer = GraphHealer(graph=graph)
    report = healer.heal_orphans()

    assert report.healed_count == 1
    assert len(report.actions_taken) == 1
    action = report.actions_taken[0]
    assert action.method == "deterministic"
    assert action.action == "restored_derivation"
    assert graph.graph.has_edge("parent_node", "child_node")


def test_similarity_link_high_confidence(graph):
    graph.add_entity({"node_id": "o1", "content": "Python programming", "deletion_state": "active"})
    graph.add_entity({"node_id": "t1", "content": "Software engineering", "deletion_state": "active"})

    fake_vs = FakeVectorStore([("t1", 0.95)])
    healer = GraphHealer(graph=graph, vector_store=fake_vs)

    report = healer.heal_orphans()
    assert report.healed_count == 1
    action = [a for a in report.actions_taken if a.node_id == "o1"][0]
    assert action.method == "vector_similarity"
    assert action.action == "similarity_link"
    assert graph.graph.has_edge("o1", "t1")
    edge_data = graph.graph.edges["o1", "t1"]
    assert edge_data.get("relationship") == "RELATED_TO"
    assert edge_data.get("confidence") == 0.95


def test_similarity_link_medium_confidence_requires_review(graph):
    graph.add_entity({"node_id": "o2", "content": "Data analysis", "deletion_state": "active"})
    graph.add_entity({"node_id": "t2", "content": "Business intelligence", "deletion_state": "active"})

    fake_vs = FakeVectorStore([("t2", 0.85)])
    healer = GraphHealer(graph=graph, vector_store=fake_vs)

    report = healer.heal_orphans()
    action = [a for a in report.actions_taken if a.node_id == "o2"][0]
    assert action.method == "vector_similarity"
    edge_data = graph.graph.edges["o2", "t2"]
    assert edge_data.get("requires_review") is True


def test_similarity_below_threshold_quarantines(graph):
    graph.add_entity({"node_id": "o3", "content": "Quantum entanglement", "deletion_state": "active"})
    graph.add_entity({"node_id": "t3", "content": "Cooking recipe", "deletion_state": "active"})

    fake_vs = FakeVectorStore([("t3", 0.50)])
    healer = GraphHealer(graph=graph, vector_store=fake_vs)

    report = healer.heal_orphans()
    action = [a for a in report.actions_taken if a.node_id == "o3"][0]
    assert action.method == "quarantine"
    assert action.action == "quarantined"
    assert graph.graph.nodes["o3"]["deletion_state"] == "quarantined"


def test_quarantine_excludes_from_active(graph):
    graph.add_entity({"node_id": "active_ent", "content": "I am active", "deletion_state": "active"})
    graph.add_entity({"node_id": "orphan_to_q", "content": "Random unlinked text", "deletion_state": "active"})

    healer = GraphHealer(graph=graph, vector_store=None)
    healer.heal_orphans()

    active_entities = graph.get_active_entities()
    active_ids = {e["node_id"] for e in active_entities}
    assert "orphan_to_q" not in active_ids


def test_no_audit_does_not_crash(graph):
    graph.add_entity({"node_id": "n_solo", "content": "Solo node"})
    healer = GraphHealer(graph=graph, audit_chain=None)
    report = healer.heal_orphans()
    assert len(report.actions_taken) >= 1


def test_audit_events_written(graph):
    graph.add_entity({"node_id": "audit_node", "content": "Check audit logging"})
    audit = FakeAudit()
    healer = GraphHealer(graph=graph, audit_chain=audit)

    healer.heal_orphans()
    operations = [op for op, _, _ in audit.events]
    assert "graph_orphan_detected" in operations
    assert ("graph_orphan_healed" in operations) or ("graph_orphan_quarantined" in operations)


def test_idempotency_no_duplicate_edges(graph):
    graph.add_entity({"node_id": "n_src", "content": "Machine learning algorithms"})
    graph.add_entity({"node_id": "n_tgt", "content": "Artificial intelligence"})

    fake_vs = FakeVectorStore([("n_tgt", 0.95)])
    healer = GraphHealer(graph=graph, vector_store=fake_vs)

    # First run heals the orphan
    rep1 = healer.heal_orphans()
    assert rep1.healed_count == 1
    assert graph.graph.has_edge("n_src", "n_tgt")

    # Second run should find 0 orphans or skip
    rep2 = healer.heal_orphans()
    assert rep2.healed_count == 0
    # Exactly 1 edge between n_src and n_tgt
    edges = [(u, v) for u, v in graph.graph.edges() if (u, v) in [("n_src", "n_tgt"), ("n_tgt", "n_src")]]
    assert len(edges) == 1


def test_idempotency_no_duplicate_quarantine(graph):
    graph.add_entity({"node_id": "q_iso", "content": "Unrepairable isolated entity"})
    healer = GraphHealer(graph=graph, vector_store=None)

    rep1 = healer.heal_orphans()
    assert "q_iso" in rep1.quarantined

    rep2 = healer.heal_orphans()
    assert len(rep2.quarantined) == 0
    assert graph.graph.nodes["q_iso"]["deletion_state"] == "quarantined"


def test_no_silent_merge(graph):
    graph.add_entity({"node_id": "ent1", "content": "Entity 1"})
    graph.add_entity({"node_id": "ent2", "content": "Entity 2"})

    healer = GraphHealer(graph=graph)
    healer.heal_orphans()

    assert graph.graph.number_of_nodes() == 2
    assert graph.has_entity("ent1") is True
    assert graph.has_entity("ent2") is True


def test_no_auto_delete(graph):
    graph.add_entity({"node_id": "to_not_delete", "content": "Do not delete me"})
    healer = GraphHealer(graph=graph)
    healer.heal_orphans()

    assert graph.has_entity("to_not_delete") is True
    assert graph.graph.nodes["to_not_delete"]["deletion_state"] == "quarantined"


@pytest.fixture
def tmp_kg(tmp_path):
    def _make():
        return KnowledgeGraph(path=str(tmp_path / "kg.json"))
    return _make


def test_find_duplicates_exact_match(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    healer = GraphHealer(graph=kg, vector_store=None)
    pairs = healer.find_duplicates(threshold=0.95)
    assert len(pairs) == 1
    assert pairs[0].similarity == pytest.approx(1.0)
    assert pairs[0].detection_method == "jaccard"


def test_find_duplicates_near_match(tmp_kg):
    kg = tmp_kg()
    # 4 of 5 words overlap -> Jaccard ~0.67. Use 0.6 threshold to hit, 0.95 to miss.
    kg.add_entity({"node_id": "a", "content": "user prefers python programming language", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "user prefers python programming tools", "entity_type": "preference", "deletion_state": "active"})
    healer = GraphHealer(graph=kg, vector_store=None)
    assert len(healer.find_duplicates(threshold=0.6)) == 1
    assert len(healer.find_duplicates(threshold=0.95)) == 0


def test_find_duplicates_no_match(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "user prefers python", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "weather is cold today", "entity_type": "fact", "deletion_state": "active"})
    healer = GraphHealer(graph=kg, vector_store=None)
    assert healer.find_duplicates(threshold=0.5) == []


def test_find_duplicates_excludes_deleted(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "source_removed"})
    healer = GraphHealer(graph=kg, vector_store=None)
    assert healer.find_duplicates(threshold=0.5) == []


def test_find_duplicates_excludes_quarantined(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "quarantined"})
    healer = GraphHealer(graph=kg, vector_store=None)
    assert healer.find_duplicates(threshold=0.5) == []


def test_find_duplicates_does_not_modify_graph(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "user prefers python programming", "entity_type": "preference", "deletion_state": "active"})
    kg.add_relationship("a", "b", "RELATED_TO")
    nodes_before = kg.graph.number_of_nodes()
    edges_before = kg.graph.number_of_edges()
    healer = GraphHealer(graph=kg, vector_store=None)
    healer.find_duplicates(threshold=0.5)
    assert kg.graph.number_of_nodes() == nodes_before
    assert kg.graph.number_of_edges() == edges_before


def test_find_duplicates_sorted_by_similarity(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "alpha beta gamma delta", "entity_type": "fact", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "alpha beta gamma delta", "entity_type": "fact", "deletion_state": "active"})
    kg.add_entity({"node_id": "c", "content": "alpha beta gamma epsilon", "entity_type": "fact", "deletion_state": "active"})
    kg.add_entity({"node_id": "d", "content": "alpha beta zeta eta", "entity_type": "fact", "deletion_state": "active"})
    healer = GraphHealer(graph=kg, vector_store=None)
    pairs = healer.find_duplicates(threshold=0.3)
    sims = [p.similarity for p in pairs]
    assert sims == sorted(sims, reverse=True)


def test_find_duplicates_uses_vector_store_when_available(tmp_kg):
    kg = tmp_kg()
    kg.add_entity({"node_id": "a", "content": "user prefers python", "entity_type": "preference", "deletion_state": "active"})
    kg.add_entity({"node_id": "b", "content": "user likes python language", "entity_type": "preference", "deletion_state": "active"})
    fake = FakeVectorStore(results=[("b", 0.97), ("a", 0.99)])
    healer = GraphHealer(graph=kg, vector_store=fake, similarity_threshold=0.82)
    pairs = healer.find_duplicates(threshold=0.95)
    assert len(pairs) == 1
    assert pairs[0].detection_method == "vector_similarity"


