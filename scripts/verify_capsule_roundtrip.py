import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.agent_a import AgentA
from capsule.export import CapsuleExporter
from capsule.import_capsule import CapsuleImporter
from capsule.validator import validate_capsule

def main():
    agent = AgentA()
    parent = agent.remember("Round-trip secret key is sk-roundtrip", "conversation_turn", "roundtrip", 1, "user_asserted")
    children = [agent.remember(text, "derived", "roundtrip", i, "derived") for i, text in enumerate(("Summary of round-trip secret", "Code config contains sk-roundtrip"), 2)]
    for child in children:
        parent.add_derivation(child.node_id, "derived")
        agent.graph_store.add_edge(parent.node_id, child.node_id, "derived")
    report = agent.forget(parent.node_id)
    capsule = CapsuleExporter().export("agent_a", list(agent.all_nodes.values()), agent.graph, agent.hash_chain, agent.residual_risks)
    target = Path("data/capsules/verify_roundtrip.json")
    target.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    valid, errors = validate_capsule(json.loads(target.read_text(encoding="utf-8")))
    print(f"VALIDATION: {valid} errors={errors}")
    nodes, meta = CapsuleImporter().import_capsule(target, "agent_b")
    imported = {node.node_id: node for node in nodes}
    assert imported[parent.node_id].is_blocked is True
    print("ASSERT deleted node imported blocked: PASS")
    assert len(meta["residual_risks"]) == len(report.residual_risks)
    print("ASSERT residual risks inherited: PASS")
    assert capsule["hash_chain"]["integrity_verified"] is True
    print("ASSERT hash chain integrity preserved: PASS")
    print("CAPSULE ROUNDTRIP PASSED")

if __name__ == "__main__":
    main()
