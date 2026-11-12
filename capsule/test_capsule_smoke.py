import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from core.provenance_graph import ProvenanceGraph
from core.residual_risk import ResidualRisk
from capsule.export import CapsuleExporter
from capsule.import_capsule import CapsuleImporter


def source():
    return {"type": "test", "session_id": "smoke", "turn_index": 0, "timestamp": "2026-11-12T00:00:00Z", "raw_reference": "smoke"}


def main():
    node1 = MemoryNode(node_id="node-1", content="active", source=source())
    node2 = MemoryNode(node_id="node-2", content="removed", source=source(), deletion_state="source_removed")
    graph = ProvenanceGraph(path="data/smoke_provenance.json")
    graph.add_node(node1); graph.add_node(node2); graph.add_edge(node1.node_id, node2.node_id, "derived")
    chain = HashChain(log_path="data/smoke_audit.json")
    chain.append("create", node1.node_id, {"source": "smoke"}); chain.append("delete", node2.node_id, {"reason": "source_removed"})
    risk = ResidualRisk(risk_type="derived_content", cluster="test", description="possible residue", severity="low", affected_node_ids=[node2.node_id])
    capsule = CapsuleExporter().export("test_agent", [node1, node2], graph, chain, [risk])
    path = Path("data/capsules") / f"cap_{capsule['capsule_id']}.json"
    assert path.exists()
    nodes, metadata = CapsuleImporter().import_capsule(str(path), "target_agent")
    assert next(n for n in nodes if n.node_id == "node-2").is_blocked is True
    assert next(n for n in nodes if n.node_id == "node-1").is_blocked is False
    assert len(metadata["residual_risks"]) == 1
    print("✅ CAPSULE SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
