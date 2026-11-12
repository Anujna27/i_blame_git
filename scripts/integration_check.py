"""Integration check: run ErasureEngine against real VectorStore and GraphStore."""
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    results = {"passed": [], "failed": []}
    def check(name, fn):
        try:
            fn(); results["passed"].append(name); print(f"[PASS] {name}")
        except Exception as e:
            results["failed"].append((name, str(e))); print(f"[FAIL] {name}: {e}"); traceback.print_exc()
    try:
        from core.memory_node import MemoryNode
        from core.hash_chain import HashChain
        from core.erasure_engine import ErasureEngine
        from scripts.faiss_vector_store import FaissVectorStore
        from stores.graph_store import GraphStore
    except Exception as e:
        print(f"[FATAL] Import failed: {e}"); traceback.print_exc(); sys.exit(1)
    source = {"type":"conversation_turn","session_id":"s1","turn_index":1,"timestamp":"2026-11-12T00:00:00Z","raw_reference":"s1_t1"}
    def check_node_schema():
        n=MemoryNode(content="test",source=source,trust_status="user_asserted"); assert n.node_id; assert n.deletion_state=="active"; assert n.is_blocked is False
    def check_vector_store_contract():
        vec=FaissVectorStore(collection_name="m1_integration_check"); assert hasattr(vec,"remove_from_active_index"); assert hasattr(vec,"query"); vec.remove_from_active_index("missing")
    def check_graph_store_contract():
        graph=GraphStore(); assert hasattr(graph,"get_node"); assert hasattr(graph,"get_descendants"); assert hasattr(graph,"get_all_active_nodes"); assert isinstance(graph.get_descendants("missing"),list); assert isinstance(graph.get_all_active_nodes(),list)
    def check_real_integration():
        parent=MemoryNode(content="User API key is sk-abc123",source=source,trust_status="user_asserted")
        children=[MemoryNode(content=x,source={**source,"type":"derived"},trust_status="derived") for x in ("Summary: user API key begins sk-","config = {key: sk-abc123}")]
        vec=FaissVectorStore(collection_name="m1_integration_full"); graph=GraphStore(); graph.add_node(parent)
        for child in children: graph.add_node(child); graph.add_edge(parent.node_id,child.node_id,"derived")
        report=ErasureEngine("data/_m1_integration_blocked.json").delete(parent.node_id,vec,graph,HashChain("data/_m1_integration_audit.json"))
        import json
        with open("data/m1_integration_report.json","w") as f: json.dump({"verdict":report.verdict,"levels":[{"n":l.level_number,"name":l.level_name,"status":l.status} for l in report.levels],"residual_risks_count":len(report.residual_risks),"signature":report.signature},f,indent=2)
        assert len(report.levels)==5; assert report.verdict in ("fully_deleted","partially_deleted","failed"); assert HashChain("data/_m1_integration_audit.json").verify_integrity()[0]
        print("[INTEGRATION REPORT]", report.verdict)
    check("MemoryNode schema",check_node_schema); check("VectorStore contract",check_vector_store_contract); check("GraphStore contract",check_graph_store_contract); check("Real end-to-end integration",check_real_integration)
    print(f"PASSED: {len(results['passed'])}\nFAILED: {len(results['failed'])}")
    if results["failed"]: sys.exit(1)
if __name__ == "__main__": main()
