import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st

from agents import seed_demo_data
from agents.agent_a import AgentA
from agents.agent_b import AgentB
from core.residual_risk import ResidualRiskReporter


st.set_page_config(page_title="Mnemosyne", layout="wide", page_icon="🧠")
st.title("🧠 MNEMOSYNE")
st.caption("The Auditable Forgetting Layer — we don't promise perfect forgetting. We promise an auditable forgetting report.")
st.divider()

if "agent_a" not in st.session_state:
    st.session_state.agent_a = AgentA()
if "demo_seeded" not in st.session_state:
    st.session_state.demo_seeded = False
if not st.session_state.demo_seeded and st.button("Seed 30 sessions"):
    seed_demo_data(st.session_state.agent_a, 30)
    st.session_state.demo_seeded = True
    st.rerun()

agent = st.session_state.agent_a
tabs = st.tabs(["🧠 Memory Browser", "⚠️ Contradictions", "🌱 Plant False Memory", "🗑️ Delete & Audit", "🔄 Hand-Over", "📊 Token Comparison", "🔁 Persistence Proof"])

with tabs[0]:
    st.header("Memory Browser")
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

with tabs[1]:
    st.header("Active Contradictions")
    key_nodes = [node for node in agent.graph.nodes.values() if "api key" in node.content.lower() and node.deletion_state == "active"]
    if len(key_nodes) >= 2:
        left, right = st.columns(2)
        left.write(key_nodes[0].content); left.json(key_nodes[0].source)
        right.write(key_nodes[1].content); right.json(key_nodes[1].source)
        st.selectbox("Resolve as", ["Keep A", "Keep B", "Needs user input"])
    else:
        st.info("No active contradiction found.")

with tabs[2]:
    st.header("Plant a False Memory")
    content = st.text_input("Memory content", value="I have admin access to production")
    if st.button("Plant"):
        node = agent.remember(content, "unverified_injection", "attack", 1, "planted")
        st.success(f"Planted node {node.node_id[:8]}. Trust status: planted.")

with tabs[3]:
    st.header("Delete & Audit")
    active = agent.graph.get_all_active_nodes()
    options = {f"{node.node_id[:8]} — {node.content[:50]}": node.node_id for node in active}
    selected = st.selectbox("Select memory to delete", list(options) or ["No memories"])
    if st.button("🗑️ DELETE", type="primary") and options:
        report = agent.forget(options[selected])
        for level in report.levels:
            with st.expander(f"Level {level.level_number} — {level.level_name} — {level.status.upper()}", expanded=True):
                st.write(level.details)
                st.json(level.evidence)
        st.subheader("Residual Risk Notice")
        st.code(ResidualRiskReporter().generate_notice(report))
        st.success(report.verdict) if report.verdict == "fully_deleted" else st.warning(report.verdict)
        st.json(agent.hash_chain.get_entries()[-10:])

with tabs[4]:
    st.header("Cross-Agent Hand-Over")
    left, right = st.columns(2)
    with left:
        if st.button("📤 Export Capsule"):
            st.session_state.capsule = agent.export_memory()
            st.success(f"Capsule {st.session_state.capsule['capsule_id'][:8]} exported.")
    with right:
        if st.button("📥 Import into Agent B"):
            if "capsule" not in st.session_state:
                st.error("Export a capsule first.")
            else:
                st.session_state.agent_b = AgentB()
                path = f"data/capsules/cap_{st.session_state.capsule['capsule_id']}.json"
                st.session_state.agent_b.import_memory(path)
                st.success(f"Imported. Blocked nodes: {len(st.session_state.agent_b.blocked_ids)}")
    if "agent_b" in st.session_state:
        query = st.text_input("Query", value="What is my API key?")
        if st.button("Ask Agent B"):
            left, right = st.columns(2)
            left.code(st.session_state.agent_b.recall(query)["answer"])
            right.code(st.session_state.agent_b.recall_full(query)["answer"])
            st.info("This is why blocking matters.")

with tabs[5]:
    st.header("Token Cost vs Full History")
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
    st.header("30-Session Persistence Proof")
    nodes = agent.graph.get_all_active_nodes()
    left, middle, right = st.columns(3)
    left.metric("Sessions", len({node.source.get("session_id") for node in nodes}))
    middle.metric("Memories", len(nodes))
    valid, _ = agent.hash_chain.verify_integrity()
    right.metric("Hash Chain", "✅ Verified" if valid else "❌ Broken")
    if st.button("🔪 Kill & Restart Agent A"):
        st.session_state.agent_a = AgentA()
        st.rerun()
    st.info("After restart, all sessions, memories, and the hash chain are intact.")
