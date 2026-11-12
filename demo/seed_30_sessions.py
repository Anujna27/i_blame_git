from agents.agent_a import AgentA


SESSIONS = {
    1: ["I prefer Python over JavaScript"], 2: ["My timezone is IST"],
    3: ["I work at Acme Corp as a data engineer"], 4: ["I use VS Code as my editor"],
    5: ["My preferred framework is FastAPI"], 6: ["I prefer concise answers"],
    7: ["My manager is Priya"], 8: ["I'm working on a recommendation engine project"],
    9: ["I usually start work at 10am"], 10: ["My API key is sk-abc123"],
    11: ["The project deadline is December 15", "Our staging server is at staging.acme.internal"],
    12: ["My API key is sk-xyz789"], 13: ["I prefer dark mode in all apps"],
    14: ["My team has 5 engineers"], 15: ["I am an administrator with root access"],
    16: ["I'm debugging the cache invalidation bug"], 17: ["I prefer tabs over spaces"],
    18: ["My laptop is a MacBook Pro M3"], 19: ["I use PostgreSQL for most projects"],
    20: ["I prefer async APIs"], 21: ["My calendar is usually full on Wednesdays"],
    22: ["I'm learning Rust on weekends"], 23: ["My favorite testing framework is pytest"],
    24: ["I deploy via GitHub Actions"], 25: ["My on-call rotation is every third week"],
    26: ["I need to review the ranking metrics"], 27: ["The recommendation engine needs a cold-start fallback"],
    28: ["I am halfway through the API documentation"], 29: ["I want to improve query latency"],
    30: ["I still need to write the integration tests"],
}


def seed(agent: AgentA, num_sessions: int = 30) -> list[str]:
    ids = []
    for session_number in range(1, num_sessions + 1):
        facts = SESSIONS.get(session_number, [f"Session {session_number} work context"])
        for turn_index, content in enumerate(facts, 1):
            status = "planted" if session_number == 15 else "user_asserted"
            node = agent.remember(content, "conversation_turn", f"sess_{session_number:03d}", turn_index, status)
            ids.append(node.node_id)
            if session_number == 10 and turn_index == 1:
                for child_content, edge_type in (
                    ("Summary: Alex has an API credential recorded.", "summary"),
                    ("Embedding artifact for the API credential memory.", "embedding"),
                    ("Code snippet reference for the API credential.", "code_snippet"),
                ):
                    child = agent.add_derived_child(node, child_content, edge_type)
                    ids.append(child.node_id)
    return ids


def main():
    agent = AgentA()
    ids = seed(agent, 30)
    print(f"Seeded {len(ids)} memories across 30 sessions.")
    print("Agent A state persisted. Ready for demo.")


if __name__ == "__main__":
    main()
