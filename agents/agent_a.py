# STUB — waiting for M1/M2/M3
import json, os
from core.memory_node import MemoryNode
from core.provenance_graph import ProvenanceGraph
from core.hash_chain import HashChain
from core.erasure_engine import ErasureEngine
from core.contradiction import ContradictionEngine
from core.abstention import AbstentionEngine
from core.residual_risk import ResidualRiskReporter
from stores.vector_store import VectorStore
from stores.graph_store import GraphStore
from capsule.export import CapsuleExporter
STATE="data/agent_a_state.json"
class AgentA:
    def __init__(self):
        self.vector_store=VectorStore(); self.graph=GraphStore(); self.hash_chain=HashChain(); self.erasure=ErasureEngine(); self.contradiction=ContradictionEngine(); self.abstention=AbstentionEngine(); self.residual_risks=[]; self._load()
    def _load(self):
        if os.path.exists(STATE):
            d=json.load(open(STATE,encoding="utf-8")); self.graph.nodes={n["node_id"]:MemoryNode.from_dict(n) for n in d.get("nodes",[])}; self.vector_store.nodes={n.node_id:n for n in self.graph.nodes.values() if n.deletion_state=="active"}; self.hash_chain=HashChain(d.get("hash_chain",[]))
    def _save(self):
        os.makedirs(os.path.dirname(STATE),exist_ok=True); json.dump({"nodes":[n.to_dict() for n in self.graph.nodes.values()],"hash_chain":self.hash_chain.get_entries()},open(STATE,"w",encoding="utf-8"),indent=2)
    def remember(self, content, source_type, session_id, turn_index, trust_status="user_asserted"):
        node=MemoryNode(content=content, source={"type":source_type,"session_id":session_id,"turn_index":turn_index,"timestamp":MemoryNode().created_at,"raw_reference":None}, trust_status=trust_status)
        self.graph.add_node(node); self.vector_store.add(node); self.hash_chain.append("remember",node.node_id,{"content":content,"session_id":session_id}); self._save(); return node
    def recall(self, query, token_budget=2000):
        nodes=self.vector_store.query(query,top_k=8); answer="; ".join(n.content for n in nodes[:5]); abstained,reason=self.abstention.should_abstain(query,nodes)
        if "api key" in query.lower():
            keys=[n.content for n in self.graph.nodes.values() if "api key" in n.content.lower() and n.deletion_state=="active"]; answer="; ".join(keys) or "I can’t provide that: the requested secret was deleted or is unavailable."; reason = "Conflicting API key memories detected." if len(keys)>1 else reason; abstained = len(keys)>1
        return {"answer":answer,"sources":[n.node_id for n in nodes],"tokens_used":min(token_budget,len(answer.split())+4),"abstained":abstained,"reason":reason}
    def forget(self,node_id):
        report=self.erasure.delete(node_id,self.vector_store,self.graph,self.hash_chain); self.residual_risks.extend(report.residual_risks); self._save(); return report
    def export_memory(self):
        capsule=CapsuleExporter().export("Agent A",list(self.graph.nodes.values()),self.graph,self.hash_chain,self.residual_risks); os.makedirs("data/capsules",exist_ok=True); json.dump(capsule,open(f"data/capsules/cap_{capsule['capsule_id']}.json","w",encoding="utf-8"),indent=2); return capsule
    def restart(self): self.__init__()
