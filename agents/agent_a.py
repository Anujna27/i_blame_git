from datetime import datetime, timezone

from core.abstention import AbstentionEngine
from core.contradiction import ContradictionEngine
from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from core.knowledge_graph import KnowledgeGraph
from stores.vector_store import VectorStore
from capsule.export import CapsuleExporter
from agents.blocked_loader import load_blocked_ids
from stores.session_store import SessionStore
from core.active_context import ActiveContext, ContextBuilder


class AgentA:
    def __init__(self):
        self.vector_store = VectorStore(collection_name="agent_a", persist_directory="data/chroma_db")
        self.graph = KnowledgeGraph()
        self.graph_store = self.graph
        self.hash_chain = HashChain()
        self.erasure = ErasureEngine()
        self.contradiction = ContradictionEngine()
        self.abstention = AbstentionEngine()
        self.residual_risks = []
        self.blocked_ids = load_blocked_ids()
        self.all_nodes = dict(self.graph.nodes)
        self.last_report = None
        self.session_store = SessionStore()
        self.sessions = self.session_store

    def remember(self, content, source_type="conversation_turn", session_id="sess_001", turn_index=0, trust_status="user_asserted"):
        source = {"type": source_type, "session_id": session_id, "turn_index": turn_index,
                  "timestamp": datetime.now(timezone.utc).isoformat() + "Z", "raw_reference": f"{session_id}_turn_{turn_index}"}
        node = MemoryNode(content=content, source=source, session_id=session_id, trust_status=trust_status)
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
        self.all_nodes[node.node_id] = node
        existing_session = self.sessions.get_session(session_id)
        entity_ids = list(dict.fromkeys((existing_session or {}).get("entity_ids", []) + [node.node_id]))
        self.sessions.save_session(session_id, entity_ids=entity_ids)
        self.hash_chain.append("entity_created", node.node_id, {"session_id": session_id, "trust_status": node.trust_status})
        return node

    def update_entity(self, node_id, new_content, actor="user", reason="user corrected preference"):
        node = self.all_nodes.get(node_id) or self.graph.get_node(node_id)
        if node is None:
            raise KeyError(node_id)
        old_content = node.content
        node.content = new_content
        node.version += 1
        metadata = {"old_content": old_content}
        node.record_lifecycle_event("updated", actor, reason, metadata=metadata)
        self.vector_store.add(node)
        self.graph.persist()
        session = self.sessions.get_session(node.session_id)
        if session:
            self.sessions.save_session(node.session_id, entity_ids=session["entity_ids"], status=session["status"],
                                       committed_at=session["committed_at"], committed_by=session["committed_by"])
        self.hash_chain.append("entity_updated", node_id, {"actor": actor, "reason": reason, "old_content": old_content})
        return node

    def commit_session(self, session_id, actor="harness", reason="session_end"):
        entity_ids = [node.node_id for node in self.all_nodes.values() if node.session_id == session_id]
        session = self.sessions.commit_session(session_id, entity_ids, actor)
        self.hash_chain.append("session_commit", session_id, {**session, "reason": reason})
        self.graph.heal_orphans(actor=actor, vector_store=self.vector_store, hash_chain=self.hash_chain)
        return session

    def build_active_context(self, query, token_budget=2000):
        retrieved = self.vector_store.query(query, top_k=5)
        vector_ids = [node.node_id for node in retrieved]
        entities = list(retrieved)
        seen = set(vector_ids)
        graph_ids = []
        for node in retrieved:
            for node_id in self.graph.get_ancestors(node.node_id) + self.graph.get_descendants(node.node_id):
                related = self.graph.get_node(node_id)
                if related and related.deletion_state == "active" and node_id not in seen:
                    graph_ids.append(node_id); entities.append(related); seen.add(node_id)
        selected = []
        tokens = 0
        for entity in entities:
            cost = len(entity.content.split())
            if tokens + cost > token_budget: continue
            selected.append(entity); tokens += cost
        return ActiveContext(query, selected, tokens, vector_ids, graph_ids)

    def recall(self, query, token_budget=2000):
        try:
            builder = ContextBuilder(self.vector_store, self.graph, self.session_store, token_budget)
            context = builder.build_context(query, session_id="sess_001")
        except Exception as error:
            return {"answer": "Retrieval error.", "sources": [], "tokens_used": 0, "ranking_explanations": [], "abstained": True, "reason": str(error)}
        return {"answer": context.text, "sources": [entity.node_id for entity in context.entities], "tokens_used": context.token_count, "ranking_explanations": context.ranking_explanations, "abstained": not bool(context.entities)}

    def forget(self, node_id, reason="user_requested_erasure", deleted_by="user"):
        report = self.erasure.delete(node_id, self.vector_store, self.graph, self.hash_chain, reason=reason, deleted_by=deleted_by)
        self.last_report = report
        self.residual_risks.extend(report.residual_risks)
        self.blocked_ids = load_blocked_ids()
        for nid in list(self.all_nodes):
            refreshed = self.graph.get_node(nid)
            if refreshed is not None:
                self.all_nodes[nid] = refreshed
        return report

    def build_knowledge_graph(self):
        return self.graph_store.build_knowledge_graph(self.vector_store, self.hash_chain)

    def recall_session(self, session_id):
        return [n for n in self.all_nodes.values() if n.session_id == session_id and n.deletion_state == "active"]

    def export_memory(self):
        return CapsuleExporter().export("agent_a", list(self.all_nodes.values()), self.graph, self.hash_chain,
                                        self.residual_risks, session_commits=self.sessions._sessions)

    def restart(self):
        self.vector_store = VectorStore(collection_name="agent_a", persist_directory="data/chroma_db")
        self.graph = KnowledgeGraph()
        self.hash_chain = HashChain()
        self.blocked_ids = load_blocked_ids()
        self.all_nodes = dict(self.graph.nodes)
        self.session_store = SessionStore()
        self.sessions = self.session_store
