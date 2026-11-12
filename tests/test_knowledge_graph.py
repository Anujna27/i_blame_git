from pathlib import Path
import pytest

from core.knowledge_graph import ALLOWED_RELATIONSHIPS, KnowledgeGraph
from core.memory_node import MemoryNode


def test_add_entity_plain_dict(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    node_data = {
        "node_id": "ent_1",
        "entity_type": "user_profile",
        "content": "Prefers dark mode",
        "session_id": "session_alpha",
    }
    stored = kg.add_entity(node_data)

    assert stored["node_id"] == "ent_1"
    assert stored["entity_type"] == "user_profile"
    assert stored["content"] == "Prefers dark mode"
    assert stored["session_id"] == "session_alpha"
    assert stored["deletion_state"] == "active"
    assert stored["version"] == 1
    assert isinstance(stored["lifecycle"], list)
    assert isinstance(stored["properties"], dict)

    assert kg.has_entity("ent_1") is True
    assert kg.has_entity("unknown_ent") is False

    fetched = kg.get_entity("ent_1")
    assert fetched is not None
    assert fetched["node_id"] == "ent_1"
    assert fetched["content"] == "Prefers dark mode"


def test_add_entity_pydantic_memory_node(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    mem_node = MemoryNode(
        node_id="mem_42",
        content="API token expires tomorrow",
        source={
            "type": "conversation_turn",
            "session_id": "sess_99",
            "turn_index": 1,
            "timestamp": "2026-11-12T14:32:00Z",
            "raw_reference": "turn_1",
        },
        trust_status="user_asserted",
    )

    stored = kg.add_entity(mem_node)
    assert stored["node_id"] == "mem_42"
    assert stored["content"] == "API token expires tomorrow"
    assert stored["session_id"] == "sess_99"
    assert stored["deletion_state"] == "active"

    fetched = kg.get_entity("mem_42")
    assert fetched is not None
    assert fetched["node_id"] == "mem_42"


def test_add_entity_update_keeps_history(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "u1", "content": "Initial content", "properties": {"tag": "first"}})
    updated = kg.add_entity({"node_id": "u1", "content": "Updated content", "properties": {"theme": "dark"}})

    assert updated["content"] == "Updated content"
    assert updated["version"] == 2
    assert len(updated["lifecycle"]) >= 1
    assert updated["lifecycle"][-1]["action"] == "update"
    assert updated["properties"]["tag"] == "first"
    assert updated["properties"]["theme"] == "dark"


def test_add_relationship_success_and_metadata(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "user_a", "content": "User A"})
    kg.add_entity({"node_id": "pref_b", "content": "Dark Mode Preference"})

    meta = {
        "actor": "agent_x",
        "confidence": 0.95,
        "source_session": "sess_100",
        "custom_key": "val",
    }
    edge_attrs = kg.add_relationship("user_a", "pref_b", "PREFERS", metadata=meta)

    assert edge_attrs["relationship"] == "PREFERS"
    assert edge_attrs["created_by"] == "agent_x"
    assert edge_attrs["confidence"] == 0.95
    assert edge_attrs["source_session"] == "sess_100"
    assert edge_attrs["custom_key"] == "val"
    assert "created_at" in edge_attrs


def test_add_relationship_validation_errors(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "n1", "content": "Node 1"})
    kg.add_entity({"node_id": "n2", "content": "Node 2"})

    with pytest.raises(ValueError, match="Source entity 'missing_source' does not exist"):
        kg.add_relationship("missing_source", "n2", "RELATED_TO")

    with pytest.raises(ValueError, match="Target entity 'missing_target' does not exist"):
        kg.add_relationship("n1", "missing_target", "RELATED_TO")

    with pytest.raises(ValueError, match="not in ALLOWED_RELATIONSHIPS"):
        kg.add_relationship("n1", "n2", "INVALID_RELATIONSHIP")


def test_remove_entity_edges(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "A"})
    kg.add_entity({"node_id": "B"})
    kg.add_entity({"node_id": "C"})

    kg.add_relationship("A", "B", "OWNS")
    kg.add_relationship("C", "A", "MENTIONS")
    kg.add_relationship("B", "C", "RELATED_TO")

    removed_count = kg.remove_entity_edges("A")
    assert removed_count == 2
    assert kg.has_entity("A") is True
    assert len(kg.get_neighbors("A", direction="both")) == 0
    # B -> C edge should still exist
    assert len(kg.get_neighbors("B", direction="out")) == 1


def test_get_neighbors_direction_and_filtering(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "A"})
    kg.add_entity({"node_id": "B"})
    kg.add_entity({"node_id": "C"})
    kg.add_entity({"node_id": "D"})

    kg.add_relationship("A", "B", "OWNS")
    kg.add_relationship("A", "C", "PREFERS")
    kg.add_relationship("D", "A", "MENTIONS")

    out_neighbors = kg.get_neighbors("A", direction="out")
    assert {n["node_id"] for n in out_neighbors} == {"B", "C"}

    filtered_out = kg.get_neighbors("A", relationship="PREFERS", direction="out")
    assert [n["node_id"] for n in filtered_out] == ["C"]

    in_neighbors = kg.get_neighbors("A", direction="in")
    assert [n["node_id"] for n in in_neighbors] == ["D"]

    both_neighbors = kg.get_neighbors("A", direction="both")
    assert {n["node_id"] for n in both_neighbors} == {"B", "C", "D"}


def test_get_related_entities_bfs(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    for nid in ["A", "B", "C", "D", "E"]:
        kg.add_entity({"node_id": nid})

    # A -> B -> C -> D
    kg.add_relationship("A", "B", "DERIVED_FROM")
    kg.add_relationship("B", "C", "DERIVED_FROM")
    kg.add_relationship("C", "D", "DERIVED_FROM")
    # A -> E with different relationship
    kg.add_relationship("A", "E", "MENTIONS")

    hop1 = kg.get_related_entities("A", max_hops=1)
    assert {n["node_id"] for n in hop1} == {"B", "E"}

    hop2 = kg.get_related_entities("A", max_hops=2)
    assert {n["node_id"] for n in hop2} == {"B", "E", "C"}
    assert "A" not in {n["node_id"] for n in hop2}

    filtered_hop2 = kg.get_related_entities("A", max_hops=2, relationship="DERIVED_FROM")
    assert {n["node_id"] for n in filtered_hop2} == {"B", "C"}


def test_get_all_entities_and_get_active_entities(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "active_1", "deletion_state": "active"})
    kg.add_entity({"node_id": "removed_1", "deletion_state": "source_removed"})
    kg.add_entity({"node_id": "invalid_1", "deletion_state": "invalidated"})
    kg.add_entity({"node_id": "quarantine_1", "deletion_state": "quarantined"})

    active_only = kg.get_active_entities()
    assert [n["node_id"] for n in active_only] == ["active_1"]

    non_deleted = kg.get_all_entities(include_deleted=False)
    assert {n["node_id"] for n in non_deleted} == {"active_1", "quarantine_1"}

    all_entities = kg.get_all_entities(include_deleted=True)
    assert {n["node_id"] for n in all_entities} == {
        "active_1",
        "removed_1",
        "invalid_1",
        "quarantine_1",
    }


def test_get_edges_with_include_deleted(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "a1", "deletion_state": "active"})
    kg.add_entity({"node_id": "a2", "deletion_state": "active"})
    kg.add_entity({"node_id": "i3", "deletion_state": "invalidated"})

    kg.add_relationship("a1", "a2", "OWNS")
    kg.add_relationship("a1", "i3", "RELATED_TO")

    active_edges = kg.get_edges(include_deleted=False)
    assert len(active_edges) == 1
    assert active_edges[0]["source"] == "a1"
    assert active_edges[0]["target"] == "a2"

    all_edges = kg.get_edges(include_deleted=True)
    assert len(all_edges) == 2


def test_persist_and_load(tmp_path: Path):
    kg_path = tmp_path / "nested" / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "x1", "content": "Knowledge X"})
    kg.add_entity({"node_id": "y1", "content": "Knowledge Y"})
    kg.add_relationship("x1", "y1", "EXTRACTED_FROM", metadata={"actor": "tester", "confidence": 0.88})

    # File should exist because add_entity/add_relationship persist
    assert kg_path.exists()

    # Load with a new KnowledgeGraph instance
    kg2 = KnowledgeGraph(path=str(kg_path))
    assert kg2.has_entity("x1") is True
    assert kg2.has_entity("y1") is True

    ent_x = kg2.get_entity("x1")
    assert ent_x is not None
    assert ent_x["content"] == "Knowledge X"

    neighbors = kg2.get_neighbors("x1", direction="out")
    assert len(neighbors) == 1
    assert neighbors[0]["node_id"] == "y1"


def test_stats(tmp_path: Path):
    kg_path = tmp_path / "kg.json"
    kg = KnowledgeGraph(path=str(kg_path))

    kg.add_entity({"node_id": "n1", "deletion_state": "active"})
    kg.add_entity({"node_id": "n2", "deletion_state": "active"})
    kg.add_entity({"node_id": "n3", "deletion_state": "source_removed"})
    kg.add_entity({"node_id": "isolated", "deletion_state": "active"})

    kg.add_relationship("n1", "n2", "OWNS")
    kg.add_relationship("n2", "n3", "DERIVED_FROM")

    stats = kg.stats()
    assert stats["node_count"] == 4
    assert stats["edge_count"] == 2
    assert stats["active_count"] == 3
    assert stats["orphan_count"] == 1
    assert stats["relationship_counts"] == {"OWNS": 1, "DERIVED_FROM": 1}

