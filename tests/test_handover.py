import pytest

from agents import AgentA, AgentB, seed_demo_data
from core.hash_chain import HashChain


def test_full_handover():
    agent_a = AgentA()
    seed_demo_data(agent_a, num_sessions=5)
    api_node = next((node for node in agent_a.all_nodes.values() if "sk-abc123" in node.content), None)
    assert api_node is not None, "API key node not found in all_nodes"
    deleted_id = api_node.node_id
    report = agent_a.forget(deleted_id)
    capsule = agent_a.export_memory()
    capsule_path = f"data/capsules/cap_{capsule['capsule_id']}.json"
    agent_b = AgentB()
    summary = agent_b.import_memory(capsule_path)
    assert deleted_id in agent_b.blocked_ids, f"Deleted node not blocked. Got: {agent_b.blocked_ids}"
    response = agent_b.recall("API key")
    assert response["abstained"] is True
    assert "requested for deletion" in response["answer"].lower()
    response_full = agent_b.recall_full("API key")
    assert response_full["abstained"] is False
    assert "sk-abc123" in response_full["answer"] or "sk-xyz789" in response_full["answer"]
    assert HashChain().verify_integrity()[0] is True
