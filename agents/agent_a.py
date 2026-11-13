import os
from datetime import datetime, timezone
from typing import Optional

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
from core.healing_scheduler import HealingScheduler
from core.entity_extractor import EntityExtractor
from core.summary_generator import SummaryGenerator
from stores.filesystem_memory import FilesystemMemory
from core.llm_config import ConfiguredLLM
from core.graph_healer import GraphHealer
from core.erasure_recovery import ErasureRecovery
from core.dreaming import HonchoDreaming


class AgentA:
    def __init__(self, data_dir: Optional[str] = None, *args, **kwargs):
        backend = kwargs.get("backend", None) or (args[0] if args else None)
        self.backend = backend
        data_dir = data_dir or kwargs.get("data_dir", None) or kwargs.get("path", None)
        self.data_dir = str(data_dir).rstrip("/\\") if data_dir else None

        if self.data_dir:
            os.makedirs(self.data_dir, exist_ok=True)
            self.vector_store = VectorStore(
                collection_name="agent_a",
                persist_directory=os.path.join(self.data_dir, "chroma_db"),
            )
            self.graph = KnowledgeGraph(path=os.path.join(self.data_dir, "knowledge_graph.json"))
            self.hash_chain = HashChain(log_path=os.path.join(self.data_dir, "audit_log.json"))
            self.erasure = ErasureEngine(blocked_set_path=os.path.join(self.data_dir, "blocked_inference.json"))
            self.session_store = SessionStore(path=os.path.join(self.data_dir, "sessions.json"))
            self.blocked_ids = load_blocked_ids(path=os.path.join(self.data_dir, "blocked_inference.json"))
        else:
            self.vector_store = VectorStore(collection_name="agent_a", persist_directory="data/chroma_db")
            self.graph = KnowledgeGraph()
            self.hash_chain = HashChain()
            self.erasure = ErasureEngine()
            self.session_store = SessionStore()
            self.blocked_ids = load_blocked_ids()

        self.erasure_engine = self.erasure
        self.graph_store = self.graph
        self.pending_erasures = self.erasure.journal.pending() if hasattr(self.erasure, "journal") and hasattr(self.erasure.journal, "pending") else []
        self.erasure_recovery = ErasureRecovery(self.erasure)
        self.contradiction = ContradictionEngine()
        self.abstention = AbstentionEngine()
        self.residual_risks = []
        self.all_nodes = dict(self.graph.nodes)
        self.last_report = None
        self.sessions = self.session_store
        self.healing_scheduler = HealingScheduler(self.build_knowledge_graph)
        self.llm = ConfiguredLLM()
        self.entity_extractor = EntityExtractor(self.llm if self.llm.enabled else None)
        self.summary_generator = SummaryGenerator(self.llm if self.llm.enabled else None)
        self.filesystem_memory = FilesystemMemory()
        self.graph_healer = GraphHealer(self.graph, self.vector_store, self.hash_chain,
                                        llm_suggester=self.llm.suggest_link if self.llm.enabled else None)
        self.dreaming = HonchoDreaming()

    def remember(self, content, source_type="conversation_turn", session_id="sess_001", turn_index=0,
                 trust_status="user_asserted", context_id=None, entity_refs=None):
        source = {"type": source_type, "session_id": session_id, "turn_index": turn_index,
                  "timestamp": datetime.now(timezone.utc).isoformat() + "Z", "raw_reference": f"{session_id}_turn_{turn_index}"}
        properties = {}
        if context_id:
            properties["erasure_context_id"] = context_id
        if entity_refs:
            properties["entity_refs"] = list(dict.fromkeys(str(ref) for ref in entity_refs))
        node = MemoryNode(content=content, source=source, session_id=session_id,
                          trust_status=trust_status, properties=properties)
        summaries = self.summary_generator.generate(content)
        node.summary_l0, node.summary_l1, node.content_l2 = summaries["l0"], summaries["l1"], summaries["l2"]
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
        node.content_l2 = new_content
        node.summary_l0 = new_content[:240]
        node.summary_l1 = new_content[:2000]
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
        entity_ids = [
            node.node_id
            for node in self.all_nodes.values()
            if node.session_id == session_id and node.deletion_state == "active"
        ]
        session_nodes = [self.all_nodes[node_id] for node_id in entity_ids if node_id in self.all_nodes]
        self.entity_extractor.extract([node.content for node in session_nodes])
        for node in session_nodes:
            self.filesystem_memory.write_entity(node)
        session = self.sessions.commit_session(session_id, entity_ids, actor)
        self.hash_chain.append("session_commit", session_id, {**session, "reason": reason})
        self.graph_healer.heal_orphans(session_id=session_id)
        session["dreaming"] = self.dream_session(
            session_id, actor=actor, reason="after_session_commit"
        )
        return session

    def dream_session(self, session_id, actor="honcho", reason="dreaming_consolidation", token_budget=256):
        """Run local Laya gating, escalate ambiguity to the configured LLM, and persist accepted memory."""
        source_nodes = [node for node in self.all_nodes.values()
                        if node.session_id == session_id
                        and node.deletion_state == "active"
                        and node.entity_type != "dream_summary"]
        decision = self.dreaming.consolidate(source_nodes, llm=self.llm if self.llm.enabled else None,
                                             token_budget=token_budget)
        report = decision.to_dict()
        report["session_id"] = session_id
        report["source_node_ids"] = [node.node_id for node in source_nodes]
        if decision.action not in {"accept", "resolved_by_llm"} or not decision.candidate.strip():
            return report

        source = {"type": "dreaming_summary", "session_id": session_id,
                  "source_node_ids": report["source_node_ids"],
                  "actor": actor, "reason": reason}
        summary = self.summary_generator.generate(decision.candidate)
        node = MemoryNode(content=decision.candidate, source=source, session_id=session_id,
                          trust_status="derived", entity_type="dream_summary",
                          properties={"dreaming_decision": report})
        node.summary_l0, node.summary_l1, node.content_l2 = summary["l0"], summary["l1"], summary["l2"]
        self.vector_store.add(node)
        self.graph.add_node(node)
        self.all_nodes[node.node_id] = node
        for parent in source_nodes:
            self.graph.add_edge(parent.node_id, node.node_id, edge_type="DERIVED_FROM",
                                 actor=actor, source_session=session_id)
        session = self.sessions.get_session(session_id) or {}
        entity_ids = list(dict.fromkeys(session.get("entity_ids", []) + [node.node_id]))
        self.sessions.save_session(session_id, entity_ids=entity_ids,
                                   status=session.get("status", "active"),
                                   committed_at=session.get("committed_at"),
                                   committed_by=session.get("committed_by"))
        self.hash_chain.append("dreaming_consolidated", node.node_id,
                               {"session_id": session_id, "actor": actor,
                                "source_node_ids": report["source_node_ids"],
                                "decision": decision.action, "reason": reason})
        report["persisted_node_id"] = node.node_id
        return report

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

    def merge_duplicate_entities(self, keep_node_id, remove_node_id, actor="user", reason="explicit_duplicate_merge"):
        from core.graph_healer import GraphHealer
        healer = GraphHealer(self.graph, self.vector_store, self.hash_chain)
        result = healer.merge_duplicate(keep_node_id, remove_node_id, actor, reason)
        self.all_nodes.pop(remove_node_id, None)
        return result

    def recall(self, query, token_budget=2000):
        try:
            builder = ContextBuilder(self.vector_store, self.graph, self.session_store, token_budget)
            context = builder.build_context(query, session_id="sess_001")
        except Exception as error:
            return {"answer": "Retrieval error.", "sources": [], "tokens_used": 0, "ranking_explanations": [], "abstained": True, "reason": str(error)}
        return {"answer": context.text, "sources": [entity.node_id for entity in context.entities], "tokens_used": context.token_count, "ranking_explanations": context.ranking_explanations, "abstained": not bool(context.entities)}

    def forget(self, node_id, reason="user_requested_erasure", deleted_by="user", context_id=None, entity_refs=None):
        report = self.erasure.delete(
            node_id,
            self.vector_store,
            self.graph,
            self.hash_chain,
            reason=reason,
            deleted_by=deleted_by,
            filesystem_store=self.filesystem_memory,
            semantic_cleanup=True,
            context_id=context_id,
            entity_refs=entity_refs,
        )
        self.last_report = report
        self.residual_risks.extend(report.residual_risks)
        if hasattr(self.sessions, "remove_ids"):
            self.sessions.remove_ids(report.erased_entity_ids, actor=deleted_by, reason=reason)
        self.blocked_ids = load_blocked_ids()
        for nid in list(self.all_nodes):
            refreshed = self.graph.get_node(nid)
            if refreshed is not None:
                self.all_nodes[nid] = refreshed
        return report

    def forget_topic(self, topic, reason="user_requested_erasure", deleted_by="user", actor=None):
        actor_name = actor or deleted_by
        results = self.vector_store.query(topic, top_k=50)
        reports = []
        for node in results:
            nid = getattr(node, "node_id", None) or (node.get("node_id") if isinstance(node, dict) else None)
            l2 = getattr(node, "content_l2", "") or getattr(node, "content", "") or ""
            if topic.lower() in l2.lower():
                r = self.forget(nid, reason=reason, deleted_by=actor_name)
                reports.append(r)
        return reports

    def build_knowledge_graph(self):
        report = self.graph_healer.heal_orphans()
        return {"orphans_found": len(report.orphans_found), "healed": report.healed_count,
                "quarantined": len(report.quarantined), "actions": [a.__dict__ for a in report.actions_taken]}

    def start_graph_healing(self, interval_seconds=900):
        self.healing_scheduler.interval_seconds = interval_seconds
        self.healing_scheduler.start()

    def stop_graph_healing(self):
        self.healing_scheduler.stop()

    def llm_telemetry(self):
        return self.llm.telemetry()

    def recover_pending_erasures(self):
        result = self.erasure_recovery.reconcile(
            self.vector_store,
            self.graph,
            self.hash_chain,
            self.filesystem_memory,
        )
        self.pending_erasures = self.erasure.journal.pending()
        return result

    def save_healing_schedule(self):
        self.healing_scheduler.save_config()

    def recall_session(self, session_id):
        return [n for n in self.all_nodes.values() if n.session_id == session_id and n.deletion_state == "active"]

    def export_memory(self):
        return CapsuleExporter().export("agent_a", list(self.all_nodes.values()), self.graph, self.hash_chain,
                                        self.residual_risks, session_commits=self.sessions._sessions, vector_store=self.vector_store)

    def restart(self):
        if self.data_dir:
            self.vector_store = VectorStore(collection_name="agent_a", persist_directory=os.path.join(self.data_dir, "chroma_db"))
            self.graph = KnowledgeGraph(path=os.path.join(self.data_dir, "knowledge_graph.json"))
            self.hash_chain = HashChain(log_path=os.path.join(self.data_dir, "audit_log.json"))
            blocked_path = os.path.join(self.data_dir, "blocked_inference.json")
            self.blocked_ids = load_blocked_ids(path=blocked_path)
            self.session_store = SessionStore(path=os.path.join(self.data_dir, "sessions.json"))
        else:
            self.vector_store = VectorStore(collection_name="agent_a", persist_directory="data/chroma_db")
            self.graph = KnowledgeGraph()
            self.hash_chain = HashChain()
            self.blocked_ids = load_blocked_ids()
            self.session_store = SessionStore()
        self.all_nodes = dict(self.graph.nodes)
        self.sessions = self.session_store
