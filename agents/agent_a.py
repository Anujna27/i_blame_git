from datetime import datetime, timezone

from core.abstention import AbstentionEngine
from core.contradiction import ContradictionEngine
from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from core.provenance_graph import ProvenanceGraph
from stores.vector_store import VectorStore
from capsule.export import CapsuleExporter
from agents.blocked_loader import load_blocked_ids
from stores.session_store import SessionStore
from core.active_context import ActiveContext
from core.context_builder import ContextBuilder


class AgentA:
    def __init__(self):
        self.vector_store = VectorStore(collection_name="agent_a", persist_directory="data/chroma_db")
        self.graph = ProvenanceGraph()
        self.graph_store = self.graph
        self.hash_chain = HashChain()
        self.erasure = ErasureEngine()
        self.contradiction = ContradictionEngine()
        self.abstention = AbstentionEngine()
        self.residual_risks = []
        self.blocked_ids = load_blocked_ids()
        self.all_nodes = {}
        self.last_report = None
        self.sessions = SessionStore()

    def remember(self, content, source_type="conversation_turn", session_id="sess_001", turn_index=0, trust_status="user_asserted"):
        source = {"type": source_type, "session_id": session_id, "turn_index": turn_index,
                  "timestamp": datetime.now(timezone.utc).isoformat() + "Z", "raw_reference": f"{session_id}_turn_{turn_index}"}
        node = MemoryNode(content=content, source=source, trust_status=trust_status)
        try:
            conflicts = self.contradiction.detect(node, self.graph.get_all_active_nodes())
            if conflicts:
                node.trust_status = "contradicted"
                for conflict in conflicts:
                    other = conflict.node_a_id if conflict.node_b_id == node.node_id else conflict.node_b_id
                    if other not in node.contradicts:
                        node.contradicts.append(other)
        except Exception as error:
            print(f"[remember] contradiction.detect failed: {error}")
        self.vector_store.add(node)
        self.graph.add_node(node)
        self.sessions.add(node)
        self.all_nodes[node.node_id] = node
        self.hash_chain.append("write", node.node_id, {"preview": content[:50], "trust_status": node.trust_status})
        return node

    def update_entity(self, node_id, content, actor="system", reason="entity_updated"):
        node = self.graph.get_node(node_id)
        if node is None:
            raise KeyError(node_id)
        old_content = node.content
        node.content = content
        node.version += 1
        node.lifecycle.append({"state": "updated", "actor": actor, "reason": reason,
                               "old_value": old_content, "new_value": content,
                               "timestamp": datetime.now(timezone.utc).isoformat()})
        self.vector_store.add(node)
        self.graph.persist()
        self.sessions.add(node)
        self.hash_chain.append("entity_updated", node_id, {"actor": actor, "reason": reason,
                                                              "old_value": old_content, "new_value": content})
        return node

    def commit_session(self, session_id, actor="harness", reason="session_end"):
        event = self.sessions.commit(session_id, actor, reason)
        self.hash_chain.append("session_commit", session_id, event)
        return event

    def build_active_context(self, query, token_budget=2000, session_id=None, weights=None):
        return ContextBuilder(self.vector_store, self.graph, self.sessions, weights).build(
            query, token_budget, session_id=session_id, blocked_ids=self.blocked_ids)

    def recall(self, query, token_budget=2000):
        try:
            retrieved = self.build_active_context(query, token_budget).entities
        except Exception as error:
            return {"answer": "Retrieval error.", "sources": [], "tokens_used": 0, "abstained": True, "reason": str(error)}
        blocked_present = any(node.node_id in self.blocked_ids for node in retrieved)
        safe = [node for node in retrieved if node.node_id not in self.blocked_ids]
        if blocked_present and not safe:
            return {"answer": "This information was requested for deletion. Source storage was cleared. Residual semantic risk remains. I cannot confirm non-inferability.", "sources": [], "tokens_used": 0, "abstained": True, "reason": "blocked_by_erasure"}
        abstain, reason = self.abstention.should_abstain(query, safe)
        if abstain:
            return {"answer": reason, "sources": [], "tokens_used": 0, "abstained": True, "reason": reason}
        tokens = sum(len(node.content.split()) for node in safe)
        return {"answer": " | ".join(node.content for node in safe), "sources": [node.node_id for node in safe], "tokens_used": tokens, "abstained": False, "reason": ""}

    def forget(self, node_id, reason="user_requested", deleted_by="system"):
        report = self.erasure.delete(node_id, self.vector_store, self.graph, self.hash_chain, reason, deleted_by)
        self.last_report = report
        self.residual_risks.extend(report.residual_risks)
        self.blocked_ids = load_blocked_ids()
        for nid in list(self.all_nodes):
            refreshed = self.graph.get_node(nid)
            if refreshed is not None:
                self.all_nodes[nid] = refreshed
        return report

    def build_knowledge_graph(self):
        return self.graph_store.build_knowledge_graph()

    def recall_session(self, session_id):
        return [n for n in self.sessions.get(session_id) if n.deletion_state == "active"]

    def export_memory(self):
        return CapsuleExporter().export("agent_a", list(self.all_nodes.values()), self.graph, self.hash_chain, self.residual_risks)

    def restart(self):
        self.vector_store = VectorStore(collection_name="agent_a", persist_directory="data/chroma_db")
        self.graph = ProvenanceGraph()
        self.hash_chain = HashChain()
        self.blocked_ids = load_blocked_ids()
