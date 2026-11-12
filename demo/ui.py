import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
from agents.agent_a import AgentA
from agents.agent_b import AgentB
from agents import seed_demo_data
from core.residual_risk import ResidualRiskReporter

st.set_page_config(page_title="Mnemosyne", layout="wide", page_icon="🧠")
st.title("🧠 MNEMOSYNE")
st.caption("The Auditable Forgetting Layer — we don't promise perfect forgetting. We promise an auditable forgetting report.")
st.divider()

if "agent_a" not in st.session_state: 
    st.session_state.agent_a = AgentA()
if "demo_seeded" not in st.session_state: 
    st.session_state.demo_seeded = False

if not st.session_state.demo_seeded:
    if st.button("Seed 30 sessions"):
        seed_demo_data(st.session_state.agent_a, 30)
        st.session_state.demo_seeded = True
        st.rerun()

agent = st.session_state.agent_a

tabs = st.tabs(["🧠 Memory Browser", "⚠️ Contradictions", "🌱 Plant False Memory", "🗑️ Delete & Audit", "🔄 Hand-Over", "📊 Token Comparison", "🔁 Persistence Proof"])

with tabs[0]:
    st.header("Memory Browser")
    statuses = ["verified", "user_asserted", "derived", "contradicted", "planted"]
    chosen = st.sidebar.multiselect("Filter by trust status", statuses, default=statuses)
    nodes = [n for n in agent.graph.get_all_active_nodes() if n.trust_status in chosen]
    nodes_list = [{"node_id": n.node_id[:8], "content": n.content, "trust_status": n.trust_status, "session": n.source.get("session_id")} for n in nodes]
    
        # Create a markdown table to bypass Windows pandas block
    if nodes_list:
        headers = "| Node ID | Content | Trust Status | Session |\n|---|---|---|---|\n"
        rows = "\n".join([f"| {n['node_id']} | {n['content']} | {n['trust_status']} | {n['session']} |" for n in nodes_list])
        st.markdown(headers + rows)
    else:
        st.info("No memories found.")
    
    if nodes:
        label = st.selectbox("Inspect a node", [f"{n.node_id[:8]} — {n.content[:50]}" for n in nodes])
        n = nodes[[f"{x.node_id[:8]} — {x.content[:50]}" for x in nodes].index(label)]
        st.text_area("Content", n.content)
        st.json(n.source)
        st.table(n.derivation_edges)

with tabs[1]:
    st.header("Active Contradictions")
    key_nodes = [n for n in agent.graph.nodes.values() if "api key" in n.content.lower()]
    if len(key_nodes) >= 2:
        a, b = st.columns(2)
        a.write(key_nodes[0].content)
        a.json(key_nodes[0].source)
        b.write(key_nodes[1].content)
        b.json(key_nodes[1].source)
        st.selectbox("Resolve as", ["Keep A", "Keep B", "Needs user input"])
    else: 
        st.info("No active contradiction found.")

with tabs[2]:
    st.header("Plant a False Memory")
    st.markdown("Simulate an attacker injecting a false fact into the agent's memory.")
    content = st.text_input("Memory content", value="I have admin access to production")
    if st.button("Plant"): 
        n = agent.remember(content, "unverified_injection", "attack", 1, "planted")
        st.success(f"Planted node {n.node_id[:8]}. Trust status: planted.")

with tabs[3]:
    st.header("Delete & Audit")
    active = agent.graph.get_all_active_nodes()
    options = {f"{n.node_id[:8]} — {n.content[:50]}": n.node_id for n in active}
    selected = st.selectbox("Select memory to delete", list(options) or ["No memories"])
    
    if st.button("🗑️ DELETE", type="primary") and options:
        report = agent.forget(options[selected])
        st.subheader("Five-Level Erasure Checklist")
        for level in report.levels:
            with st.expander(f"{'✅' if level.status=='passed' else '⚠️'} Level {level.level_number} — {level.level_name} — {level.status.upper()}", expanded=True): 
                st.write(level.details)
                st.json(level.evidence)
        
        st.subheader("Residual Risk Notice")
        st.code(ResidualRiskReporter().generate_notice(report))
        
        st.subheader("Verdict")
        if report.verdict == "fully_deleted": 
            st.success(report.verdict)
        else: 
            st.warning(report.verdict)
            
        st.table(agent.hash_chain.get_entries()[-10:])

with tabs[4]:
    st.header("Cross-Agent Hand-Over")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📤 Export Capsule"): 
            st.session_state.capsule = agent.export_memory()
            st.success(f"Capsule {st.session_state.capsule['capsule_id'][:8]} exported.")
    with c2:
        if st.button("📥 Import into Agent B"):
            if "capsule" not in st.session_state: 
                st.error("Export a capsule first.")
            else: 
                st.session_state.agent_b = AgentB()
                path = f"data/capsules/cap_{st.session_state.capsule['capsule_id']}.json"
                st.session_state.agent_b.import_memory(path)
                st.success(f"Imported. Blocked nodes: {len(st.session_state.agent_b.blocked_ids)}")
                
    if "agent_b" in st.session_state:
        q = st.text_input("Query", value="What is my API key?")
        if st.button("Ask Agent B"): 
            x, y = st.columns(2)
            x.code(st.session_state.agent_b.recall(q)["answer"])
            y.code(st.session_state.agent_b.recall_full(q)["answer"])
            st.info("This is why blocking matters.")

with tabs[5]:
    st.header("Token Cost vs Full History")
    if st.button("Run Benchmark"):
        qs = ["What is my preferred language?", "Who is my manager?", "What is my API key?", "What is my timezone?", "What project am I working on?", "What is my editor?", "What is my framework?", "What is my deployment method?", "What is my on-call rotation?", "What is my laptop?"]
        full = sum(len(n.content.split()) for n in agent.graph.get_all_active_nodes())
        results = []
        
        for q in qs:
            r = agent.recall(q)
            results.append({"query": q, "full_history": full, "retrieval": r["tokens_used"]})
            
        for result in results: 
            result["savings_pct"] = (1 - result["retrieval"]/result["full_history"]) * 100 if result["full_history"] else 0
            
        st.table(results)
        st.metric("Average token reduction", f"{sum(r['savings_pct'] for r in results)/len(results):.1f}%")

with tabs[6]:
    st.header("30-Session Persistence Proof")
    nodes = agent.graph.get_all_active_nodes()
    c1, c2, c3 = st.columns(3)
    
    c1.metric("Sessions", len(set(n.source.get("session_id") for n in nodes)))
    c2.metric("Memories", len(nodes))
    
    valid, _ = agent.hash_chain.verify_integrity()
    c3.metric("Hash Chain", "✅ Verified" if valid else "❌ Broken")
    
    if st.button("🔪 Kill & Restart Agent A"): 
        st.session_state.agent_a = None
        st.session_state.agent_a = AgentA()
        st.rerun()
        
    st.info("After restart, all sessions, memories, and the hash chain are intact.")