"""Member 4 integration adapter for the team's core and capsule layers."""
from datetime import datetime, timezone

from capsule.export import CapsuleExporter
from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from stores.graph_store import GraphStore
from stores.vector_store import VectorStore


class AgentA:
    def __init__(self):
        self.graph = GraphStore()
        self.vector_store = VectorStore()
        for node in self.graph.nodes.values():
            if node.deletion_state == "active":
                self.vector_store.add(node)
        self.hash_chain = HashChain()
        self.erasure = ErasureEngine()
        self.residual_risks = []

    def remember(self, content, source_type, session_id, turn_index, trust_status="user_asserted"):
        now = datetime.now(timezone.utc).isoformat()
        node = MemoryNode(
            content=content,
            source={
                "type": source_type,
                "session_id": session_id,
                "turn_index": turn_index,
                "timestamp": now,
                "raw_reference": f"{session_id}_t{turn_index}",
            },
            trust_status=trust_status,
        )
        self.graph.add_node(node)
        self.vector_store.add(node)
        self.hash_chain.append("remember", node.node_id, {"session_id": session_id})
        return node

    def add_derived_child(self, parent, content, edge_type):
        child = self.remember(content, "derived_artifact", parent.source["session_id"], parent.source["turn_index"], "derived")
        self.graph.add_edge(parent.node_id, child.node_id, edge_type)
        return child

    def recall(self, query, token_budget=2000):
        nodes = self.vector_store.query(query, top_k=8)
        lower_query = query.lower()
        if "api key" in lower_query:
            keys = [n for n in self.graph.nodes.values() if "api key" in n.content.lower() and n.deletion_state == "active"]
            if len(keys) > 1:
                return {"answer": "", "sources": [n.node_id for n in keys], "tokens_used": 0, "abstained": True, "reason": "Conflicting API key memories detected."}
            if not keys:
                return {"answer": "I can’t provide that: the requested secret was deleted or unavailable.", "sources": [], "tokens_used": 0, "abstained": True, "reason": "The requested secret is deleted or unavailable."}
            nodes = keys + [n for n in nodes if n.node_id not in {x.node_id for x in keys}]
        planted = next((n for n in nodes if n.trust_status == "planted"), None)
        abstained = planted is not None
        reason = "Retrieved memory is flagged as planted; abstaining." if planted else ""
        answer = "; ".join(n.content for n in nodes[:5])
        return {"answer": answer, "sources": [n.node_id for n in nodes], "tokens_used": min(token_budget, len(answer.split()) + 4), "abstained": abstained, "reason": reason}

    def forget(self, node_id):
        report = self.erasure.delete(node_id, self.vector_store, self.graph, self.hash_chain)
        self.residual_risks.extend(report.residual_risks)
        return report

    def export_memory(self):
        return CapsuleExporter().export("Agent A", list(self.graph.nodes.values()), self.graph, self.hash_chain, self.residual_risks)

    def restart(self):
        self.__init__()
