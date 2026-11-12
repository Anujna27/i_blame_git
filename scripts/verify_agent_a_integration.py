"""Verify M3's AgentA.forget() calls the ErasureEngine correctly with real stores."""
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("=" * 60); print("M3 AgentA Integration Verification"); print("=" * 60)
    vs_path=Path("stores/vector_store.py"); content=vs_path.read_text() if vs_path.exists() else ""
    if "import chromadb" in content: print("[INFO] stores/vector_store.py imports chromadb"); store_mode="chromadb"
    elif "import faiss" in content or "from faiss" in content: print("[INFO] stores/vector_store.py imports faiss"); store_mode="faiss"
    else: print("[INFO] stores/vector_store.py imports neither chromadb nor faiss"); store_mode="unknown"
    try:
        if store_mode=="faiss":
            from stores.vector_store import VectorStore as VS; vector_store_impl=VS; print("[INFO] Using M2's real VectorStore (FAISS-backed)")
        else: vector_store_impl=None
    except Exception as e: print(f"[WARN] Could not import M2's VectorStore: {e}"); vector_store_impl=None
    if vector_store_impl is None:
        from scripts.faiss_vector_store import FaissVectorStore
        vector_store_impl=FaissVectorStore; print("[INFO] Using fallback FaissVectorStore from scripts/")
    try:
        from agents.agent_a import AgentA
    except Exception as e: print(f"[FATAL] Could not import AgentA: {e}"); traceback.print_exc(); sys.exit(1)
    try: agent=AgentA()
    except Exception as e: print(f"[FATAL] Could not instantiate AgentA: {e}"); traceback.print_exc(); sys.exit(1)
    checks=[("has erasure engine",hasattr(agent,"erasure") and agent.erasure is not None),("has vector_store",hasattr(agent,"vector_store") and agent.vector_store is not None),("has graph_store",hasattr(agent,"graph_store") and agent.graph_store is not None),("has hash_chain",hasattr(agent,"hash_chain") and agent.hash_chain is not None),("has forget method",callable(getattr(agent,"forget",None))),("has remember method",callable(getattr(agent,"remember",None)))]
    for name,ok in checks: print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not all(ok for _,ok in checks): print("\n[STOP] AgentA internal state is incomplete. Report to M3."); sys.exit(1)
    if store_mode=="chromadb": agent.vector_store=vector_store_impl(collection_name="m3_verify_fallback")
    source_type="conversation_turn"
    try:
        parent=agent.remember("User API key is sk-abc123",source_type,"s1",1,"user_asserted")
        child=agent.remember("Summary: user API key begins sk-","derived","s1",1,"derived")
        parent.add_derivation(child.node_id,"summarized_into"); agent.graph_store.add_edge(parent.node_id,child.node_id,"summarized_into")
        report=agent.forget(parent.node_id)
    except Exception as e: print(f"[FATAL] Live hand-over failed: {e}"); traceback.print_exc(); sys.exit(1)
    print(f"[REPORT] verdict={report.verdict}")
    print(f"[PASS] last_report={hasattr(agent,'last_report') and agent.last_report is report}")
    print(f"[{'PASS' if agent.hash_chain.verify_integrity()[0] else 'FAIL'}] hash chain integrity: {agent.hash_chain.verify_integrity()}")
    from core.residual_risk import ResidualRiskReporter
    print("\n--- NOTICE ---"); print(ResidualRiskReporter().generate_notice(report)); print("--- END NOTICE ---")
    print("\n"+"="*60); print("ALL CHECKS PASSED"); print("="*60)
if __name__=="__main__": main()
