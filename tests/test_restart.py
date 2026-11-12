from demo.demo_runner import reset_demo_state
from agents.agent_a import AgentA
from agents import seed_demo_data


def test_restart_preserves_state():
    reset_demo_state()
    agent = AgentA()
    seed_demo_data(agent, 30)
    node_count_before = len(agent.graph.get_all_active_nodes())
    session_ids_before = {n.source["session_id"] for n in agent.graph.get_all_active_nodes()}
    del agent
    new_agent = AgentA()
    node_count_after = len(new_agent.graph.get_all_active_nodes())
    session_ids_after = {n.source["session_id"] for n in new_agent.graph.get_all_active_nodes()}
    assert node_count_after == node_count_before
    assert session_ids_after == session_ids_before
    assert len(session_ids_after) >= 30
    is_valid, errors = new_agent.hash_chain.verify_integrity()
    assert is_valid, errors


def test_deletion_state_survives_restart():
    reset_demo_state()
    agent = AgentA()
    seed_demo_data(agent, 5)
    target = agent.graph.get_all_active_nodes()[0]
    agent.forget(target.node_id)
    del agent
    new_agent = AgentA()
    reloaded = new_agent.graph.get_node(target.node_id)
    assert reloaded is not None
    assert reloaded.deletion_state != "active"
