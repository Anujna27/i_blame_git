import os
import sys
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st

from agents import seed_demo_data
from agents.agent_a import AgentA
from agents.agent_b import AgentB
from core.residual_risk import ResidualRiskReporter


st.set_page_config(page_title="Mnemosyne", layout="wide")
st.title("MNEMOSYNE")
st.caption("An auditable memory system that can explain what it forgot, what it retained, and where uncertainty remains.")
st.divider()

if "agent_a" not in st.session_state or "reason" not in inspect.signature(st.session_state.agent_a.forget).parameters:
    st.session_state.agent_a = AgentA()
if "demo_seeded" not in st.session_state:
    st.session_state.demo_seeded = False
if not st.session_state.demo_seeded and st.button("Seed 30 sessions"):
    seed_demo_data(st.session_state.agent_a, 30)
    st.session_state.demo_seeded = True
    st.rerun()

agent = st.session_state.agent_a
tabs = st.tabs(["Memory Browser", "Contradictions", "Plant False Memory", "Delete and Audit", "Agent Hand-Over", "Token Comparison", "Persistence Proof"])

with tabs[0]:
    st.header("Memory Browser")
    st.write("Review the memories currently available to the agent and inspect their source and provenance.")
    statuses = ["verified", "user_asserted", "derived", "contradicted", "planted"]
    chosen = st.sidebar.multiselect("Filter by trust status", statuses, default=statuses)
    nodes = [node for node in agent.graph.get_all_active_nodes() if node.trust_status in chosen]
    st.json([{"node_id": node.node_id[:8], "content": node.content, "trust_status": node.trust_status, "session": node.source.get("session_id")} for node in nodes])
    if nodes:
        labels = [f"{node.node_id[:8]} — {node.content[:50]}" for node in nodes]
        selected = st.selectbox("Inspect a node", labels)
        node = nodes[labels.index(selected)]
        st.text_area("Content", node.content)
        st.json(node.source)
        st.json(node.derivation_edges)
        st.subheader("Lifecycle history")
        st.json(getattr(node, "lifecycle", []))
        st.subheader("Related entities")
        related = []
        for related_id in agent.graph.get_descendants(node.node_id) + agent.graph.get_ancestors(node.node_id):
            related_node = agent.graph.get_node(related_id)
            if related_node:
                related.append({"node_id": related_id, "content": related_node.content, "deletion_state": related_node.deletion_state})
        st.json(related)
        if hasattr(agent.graph, "graph"):
            dot = ["digraph provenance {"]
            for graph_id in agent.graph.graph.nodes:
                graph_node = agent.graph.get_node(graph_id)
                if graph_node:
                    color = "gray" if graph_node.deletion_state != "active" else "lightblue"
                    dot.append(f'"{graph_id}" [label="{graph_id[:8]}", style=filled, fillcolor="{color}"];')
            for source_id, target_id, edge_data in agent.graph.graph.edges(data=True):
                edge_type = edge_data.get("type", "related")
                dot.append(f'"{source_id}" -> "{target_id}" [label="{edge_type}"];')
            dot.append("}")
            st.graphviz_chart("\n".join(dot), use_container_width=True)

with tabs[1]:
    st.header("Active Contradictions")
    key_nodes = [node for node in agent.graph.nodes.values() if "api key" in node.content.lower() and node.deletion_state == "active"]
    if len(key_nodes) >= 2:
        left, right = st.columns(2)
        left.write(key_nodes[0].content); left.json(key_nodes[0].source)
        right.write(key_nodes[1].content); right.json(key_nodes[1].source)
        st.selectbox("How should this conflict be resolved?", ["Keep the first memory", "Keep the second memory", "Needs user input"])
    else:
        st.info("No active contradiction found.")

with tabs[2]:
    st.header("Plant a False Memory")
    st.write("Add an unverified memory to see how the agent handles information without a trustworthy source.")
    content = st.text_input("Memory content", value="I have admin access to production")
    if st.button("Plant"):
        node = agent.remember(content, "unverified_injection", "attack", 1, "planted")
        st.success(f"Planted node {node.node_id[:8]}. Trust status: planted.")

with tabs[3]:
    st.header("Delete and Audit")
    st.write("Delete a memory and review each stage of the erasure process, including any remaining risk.")
    active = agent.graph.get_all_active_nodes()
    options = {f"{node.node_id[:8]} — {node.content[:50]}": node.node_id for node in active}
    selected = st.selectbox("Select memory to delete", list(options) or ["No memories"])
    deletion_reason = st.text_input("Reason for deletion", value="user_requested_erasure")
    deleted_by = st.text_input("Deleted by", value="user")
    if st.button("Delete memory", type="primary") and options:
        report = agent.forget(options[selected], reason=deletion_reason, deleted_by=deleted_by)
        st.json({"entity_id": report.node_id, "entity_type": report.entity_type, "deleted_by": report.deleted_by, "deleted_at": report.timestamp, "reason": report.reason, "verdict": report.verdict})
        for level in report.levels:
            with st.expander(f"Level {level.level_number} — {level.level_name} — {level.status.upper()}", expanded=True):
                st.write(level.details)
                st.json(level.evidence)
        st.subheader("Residual Risk Notice")
        st.code(ResidualRiskReporter().generate_notice(report))
        if report.verdict == "partially_deleted":
            st.warning(report.verdict)
        else:
            st.success(report.verdict)
        st.json(agent.hash_chain.get_entries()[-10:])

with tabs[4]:
    st.header("Agent Hand-Over")
    st.write("Export memory with its deletion history, then import it into a second agent.")
    left, right = st.columns(2)
    with left:
        if st.button("Export memory"):
            st.session_state.capsule = agent.export_memory()
            st.success(f"Capsule {st.session_state.capsule['capsule_id'][:8]} exported.")
    with right:
        if st.button("Import into Agent B"):
            if "capsule" not in st.session_state:
                st.error("Export a capsule first.")
            else:
                st.session_state.agent_b = AgentB()
                path = f"data/capsules/cap_{st.session_state.capsule['capsule_id']}.json"
                summary = st.session_state.agent_b.import_memory(path)
                st.session_state.agent_b_import_summary = summary
                st.success(f"Imported {summary['imported']} nodes. Blocked nodes: {summary['blocked']}. Risks inherited: {summary['risks']}.")
    if "agent_b" in st.session_state:
        query = st.text_input("Query", value="What is my API key?")
        if st.button("Ask Agent B"):
            left, right = st.columns(2)
            left.code(st.session_state.agent_b.recall(query)["answer"])
            right.code(st.session_state.agent_b.recall_full(query)["answer"])
            st.info("Agent B inherits the deletion record, so it can refuse to use blocked memories.")

with tabs[5]:
    st.header("Token Cost Compared with Full History")
    st.write("Compare the cost of searching the complete memory history with retrieving only relevant memories.")
    if st.button("Run Benchmark"):
        queries = ["What is my preferred language?", "Who is my manager?", "What is my API key?", "What is my timezone?", "What project am I working on?", "What is my editor?", "What is my framework?", "What is my deployment method?", "What is my on-call rotation?", "What is my laptop?"]
        full_history = sum(len(node.content.split()) for node in agent.graph.get_all_active_nodes())
        results = []
        for query in queries:
            result = agent.recall(query)
            results.append({"query": query, "full_history": full_history, "retrieval": result["tokens_used"]})
        for result in results:
            result["savings_pct"] = (1 - result["retrieval"] / result["full_history"]) * 100 if result["full_history"] else 0
        st.json(results)
        st.metric("Average token reduction", f"{sum(result['savings_pct'] for result in results) / len(results):.1f}%")

with tabs[6]:
    st.header("Persistence Proof")
    st.write("Confirm that sessions, memories, and the audit chain survive an agent restart.")
    nodes = agent.graph.get_all_active_nodes()
    left, middle, right = st.columns(3)
    left.metric("Sessions", len({node.source.get("session_id") for node in nodes}))
    middle.metric("Memories", len(nodes))
    valid, _ = agent.hash_chain.verify_integrity()
    right.metric("Hash Chain", "Verified" if valid else "Broken")
    if st.button("Restart Agent A"):
        st.session_state.agent_a = AgentA()
        st.rerun()
    st.info("Restarting the agent reloads its persisted memories and audit history.")
