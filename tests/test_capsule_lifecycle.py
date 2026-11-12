from datetime import datetime, timezone

from capsule.export import CapsuleExporter
from capsule.import_capsule import CapsuleImporter
from capsule.validator import validate_capsule
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from core.provenance_graph import ProvenanceGraph


def test_capsule_round_trip_preserves_lifecycle_and_graph(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = {"type": "test", "session_id": "sess_001", "turn_index": 0, "timestamp": datetime.now(timezone.utc).isoformat(), "raw_reference": "test"}
    node_a = MemoryNode(content="Alex prefers Python", source=source)
    node_b = MemoryNode(content="Python preference summary", source=source, trust_status="derived")
    node_a.lifecycle = [{"event_id": "evt-1", "state": "created", "actor": "user", "reason": "captured", "timestamp": datetime.now(timezone.utc).isoformat(), "metadata": {}}]
    graph = ProvenanceGraph(path="graph.json")
    graph.add_node(node_a); graph.add_node(node_b); graph.add_edge(node_a.node_id, node_b.node_id, "DERIVED_FROM")
    chain = HashChain("audit.json")
    chain.append("entity_created", node_a.node_id, {}, actor="user", reason="captured")
    capsule = CapsuleExporter().export("agent_a", [node_a, node_b], graph, chain, [])
    valid, errors = validate_capsule(capsule)
    assert valid, errors
    path = tmp_path / "data" / "capsules" / f"cap_{capsule['capsule_id']}.json"
    nodes, metadata = CapsuleImporter().import_capsule(path, "agent_b")
    imported = next(node for node in nodes if node.node_id == node_a.node_id)
    assert imported.lifecycle[0]["state"] == "created"
    assert metadata["graph"]["edges"][0]["type"] == "DERIVED_FROM"
