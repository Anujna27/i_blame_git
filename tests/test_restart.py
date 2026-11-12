import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agents.agent_a import AgentA
from agents import seed_demo_data
from demo.demo_runner import reset_demo_state
def test_restart_preserves_state():
    reset_demo_state()
    agent=AgentA(); seed_demo_data(agent,30); before=len(agent.graph.get_all_active_nodes()); sessions=set(n.source["session_id"] for n in agent.graph.get_all_active_nodes()); del agent; new=AgentA(); after=len(new.graph.get_all_active_nodes()); assert after==before; assert {n.source["session_id"] for n in new.graph.get_all_active_nodes()}==sessions; assert len(sessions)>=30; assert new.hash_chain.verify_integrity()[0]
def test_deletion_state_survives_restart():
    reset_demo_state()
    agent=AgentA(); seed_demo_data(agent,5); target=agent.graph.get_all_active_nodes()[0]; agent.forget(target.node_id); del agent; new=AgentA(); reloaded=new.graph.get_node(target.node_id); assert reloaded is not None; assert reloaded.deletion_state != "active"
