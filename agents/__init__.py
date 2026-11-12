from .agent_a import AgentA
from .agent_b import AgentB


def seed_demo_data(agent, num_sessions=30):
    from demo.seed_30_sessions import seed
    return seed(agent, num_sessions)


__all__ = ["AgentA", "AgentB", "seed_demo_data"]
