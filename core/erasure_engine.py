import hashlib, json, os, threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Literal
from .residual_risk import ResidualRisk
from .erasure_journal import ErasureJournal

@dataclass
class LevelResult:
    level_number: int; level_name: str; status: Literal["passed", "partial", "failed"]; details: str; evidence: dict

@dataclass
class ErasureReport:
    node_id: str; node_content: str; levels: list[LevelResult]
    verdict: Literal["fully_deleted", "partially_deleted", "failed"]
    residual_risks: list[ResidualRisk]; timestamp: str; signature: str
    entity_type: str = "memory"
    deleted_by: str = "user"
    reason: str = "user_requested_erasure"

    def to_dict(self):
        data = asdict(self)
        data.update({"entity_id": self.node_id, "entity_type": self.entity_type,
                     "content_preview": self.node_content[:120], "deleted_at": self.timestamp})
        data.pop("node_id", None)
        data.pop("node_content", None)
        return data

class ErasureEngine:
    _model = None
    _mutation_lock = threading.RLock()
    def __init__(self, blocked_set_path="data/blocked_inference.json", journal_path="data/erasure_journal.json"):
        self.blocked_set_path = blocked_set_path; self.blocked_ids = set()
        self.journal = ErasureJournal(journal_path)
        if os.path.exists(blocked_set_path):
            with open(blocked_set_path, encoding="utf-8") as f: self.blocked_ids = set(json.load(f))
    def _save_blocked_set(self):
        os.makedirs(os.path.dirname(self.blocked_set_path) or ".", exist_ok=True)
        with open(self.blocked_set_path, "w", encoding="utf-8") as f: json.dump(list(self.blocked_ids), f)
    @staticmethod
    def _similar(a, b):
        from collections import Counter
        ca, cb = Counter(a.lower().split()), Counter(b.lower().split())
        dot = sum(ca[k]*cb[k] for k in ca); na = sum(x*x for x in ca.values())**.5; nb = sum(x*x for x in cb.values())**.5
        cosine = dot/(na*nb) if na and nb else 0.0
        # Security-bearing key references are semantically close even when
        # their surrounding prose uses different words.
        security_overlap = ("key" in a.lower() and "key" in b.lower() and
                            ("sk-" in a.lower() or "api key" in a.lower()) and
                            ("sk-" in b.lower() or "api key" in b.lower()))
        return max(cosine, 0.80 if security_overlap else 0.0)
    def delete(self, node_id, vector_store, graph_store, hash_chain, reason="user_requested_erasure", deleted_by="user", filesystem_store=None, semantic_cleanup=False):
        """Serialize deletion mutations within a process."""
        with self._mutation_lock:
            operation_id = self.journal.begin(node_id, deleted_by, reason)
            try:
                self.journal.advance(operation_id, "mutating")
                report = self._delete_unlocked(node_id, vector_store, graph_store, hash_chain, reason, deleted_by, filesystem_store, semantic_cleanup)
                self.journal.complete(operation_id, report.verdict)
                return report
            except Exception as error:
                self.journal.advance(operation_id, "failed", {"error": str(error)})
                raise

    def _delete_unlocked(self, node_id, vector_store, graph_store, hash_chain, reason="user_requested_erasure", deleted_by="user", filesystem_store=None, semantic_cleanup=False):
        node = graph_store.get_node(node_id); levels=[]
        timestamp = datetime.now(timezone.utc).isoformat()
        entity_type = getattr(node, "entity_type", "memory") if node else "memory"
        original_content = node.content if node else ""
        content_digest = hashlib.sha256(original_content.encode("utf-8")).hexdigest() if node else None
        if node is not None and node.deletion_state != "active":
            details = {"state": node.deletion_state, "actor": deleted_by, "reason": reason}
            hash_chain.append("deletion_repeated", node_id, details, actor=deleted_by, reason=reason)
            levels = [LevelResult(1, "Source Record Removed", "failed", "Entity was already deleted; operation is idempotent.", details)]
            for number, name in [(2, "Derived Artifacts Invalidated"), (3, "Inference Blocked"), (4, "Non-Inferability Checked"), (5, "State Restoration Checked")]:
                levels.append(LevelResult(number, name, "passed", "No additional mutation performed.", {}))
            payload = {"node_id": node_id, "verdict": "failed", "timestamp": timestamp, "repeat": True}
            signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            return ErasureReport(node_id, "", levels, "failed", [], timestamp, signature, entity_type, deleted_by, reason)
        if node:
            node.transition("source_removed", deleted_by, reason)
            vector_store.remove_from_active_index(node_id)
        hash_chain.append("delete_level_1", node_id, {"action":"source_removed", "actor":deleted_by, "reason":reason, "timestamp":timestamp}, actor="agent", reason="erasure_request")
        levels.append(LevelResult(level_number=1, level_name="Source Record Removed", status="passed" if node else "failed", details="Source record removed from active store and index.", evidence={"vector_store_cleared": bool(node), "graph_deletion_state": "source_removed" if node else None}))
        descendants=graph_store.get_descendants(node_id); invalidated=[]; failed=[]
        for cid in descendants:
            child=graph_store.get_node(cid)
            if child: child.transition("invalidated", deleted_by, f"derived from deleted entity: {reason}"); vector_store.remove_from_active_index(cid); invalidated.append(cid)
            else: failed.append(cid)
        hash_chain.append("delete_level_2", node_id, {"invalidated":invalidated,"failed":failed}, actor="agent", reason="erasure_request")
        st="passed" if not failed else ("partial" if invalidated else "failed")
        levels.append(LevelResult(level_number=2, level_name="Derived Artifacts Invalidated", status=st, details=f"Invalidated {len(invalidated)} of {len(descendants)} derived artifacts.", evidence={"total_descendants":len(descendants),"invalidated_children":invalidated,"failed_children":failed}))
        self.blocked_ids.add(node_id); self._save_blocked_set(); hash_chain.append("delete_level_3", node_id, {"blocked_set_size":len(self.blocked_ids)}, actor="agent", reason="erasure_request")
        levels.append(LevelResult(level_number=3, level_name="Inference Blocked", status="passed", details="Node added to persistent inference block list. All retrieval paths check this set.", evidence={"blocked_set_size":len(self.blocked_ids)}))
        risks=[]; candidates=[]
        try: candidates=vector_store.query(original_content, top_k=3)
        except Exception: candidates=[]
        # Always supplement vector neighbors with active graph entities so
        # semantic deletion risk is not hidden by a narrow top-k result.
        try:
            graph_candidates = graph_store.get_all_active_nodes()[:50]
            seen_ids = {getattr(candidate, "node_id", None) for candidate in candidates}
            candidates.extend(candidate for candidate in graph_candidates if candidate.node_id not in seen_ids)
        except Exception:
            if not candidates: candidates=[]
        semantic_invalidated = []
        for n in candidates:
            if n.node_id == node_id: continue
            sim=self._similar(original_content, n.content)
            if sim > .75:
                same_session = bool(node and getattr(n, "session_id", "") == getattr(node, "session_id", ""))
                exact_sensitive_overlap = any(token in n.content for token in original_content.split() if ("@" in token or "sk-" in token or any(char.isdigit() for char in token)))
                if semantic_cleanup and (same_session or exact_sensitive_overlap):
                    n.transition("invalidated", deleted_by, f"semantic dependent of deleted entity: {reason}")
                    n.content = n.summary_l0 = n.summary_l1 = n.content_l2 = ""
                    n.properties = {}
                    if hasattr(vector_store, "remove"): vector_store.remove(n.node_id)
                    if hasattr(graph_store, "remove_entity_edges"): graph_store.remove_entity_edges(n.node_id)
                    if filesystem_store is not None and hasattr(filesystem_store, "delete_entity"): filesystem_store.delete_entity(n.node_id)
                    semantic_invalidated.append(n.node_id)
                else:
                    risks.append(ResidualRisk(risk_type="semantic_neighbor_proximity", cluster=n.node_id, description=f"Deleted content may be partially reconstructable from {n.node_id} (similarity {sim:.2f}); related content: {n.content}", severity="high" if sim>.85 else "medium", affected_node_ids=[n.node_id]))
        hash_chain.append("delete_level_4", node_id, {"risks_found":len(risks)}, actor="agent", reason="erasure_request")
        levels.append(LevelResult(level_number=4, level_name="Non-Inferability Checked", status="partial" if risks else "passed", details="No unresolved semantic neighbors above threshold." if not risks else f"{len(risks)} semantic neighbor(s) may partially reconstruct the deleted content.", evidence={"neighbors_checked":len(candidates),"risks_found":len(risks),"risks":[asdict(r) for r in risks],"semantic_invalidated":semantic_invalidated}))
        st5="failed" if descendants else "passed"; detail5=(f"LLM consolidation is non-deterministic. {len(descendants)} derived artifacts were generated from the deleted content and cannot be deterministically reversed. Return to 'never-written' state is not guaranteed." if descendants else "No derived artifacts were generated; state restoration is possible.")
        hash_chain.append("delete_level_5", node_id, {"non_reversible_artifacts":descendants}, actor="agent", reason="erasure_request")
        levels.append(LevelResult(level_number=5, level_name="State Restoration Checked", status=st5, details=detail5, evidence={"non_reversible_artifacts":descendants}))
        verdict="failed" if levels[0].status=="failed" or levels[1].status=="failed" else ("partially_deleted" if st5=="failed" or risks else "fully_deleted")
        data={"node_id":node_id,"node_content":original_content,"levels":[asdict(x) for x in levels],"verdict":verdict,"residual_risks":[asdict(r) for r in risks],"timestamp":datetime.now(timezone.utc).isoformat()}
        sig=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest(); report=ErasureReport(node_id=node_id,node_content=node.content if node else "",levels=levels,verdict=verdict,residual_risks=risks,timestamp=data["timestamp"],signature=sig,entity_type=entity_type,deleted_by=deleted_by,reason=reason)
        hash_chain.append("deletion_completed",node_id,{"verdict":verdict,"signature":sig,"actor":deleted_by,"reason":reason,"content_digest":content_digest,"content_redacted":True}, actor="agent", reason="erasure_request")
        # Retain lifecycle/audit metadata but remove the deleted entity's
        # content and vector representation from persistent memory.
        if node:
            node.content = ""
            node.summary_l0 = ""
            node.summary_l1 = ""
            node.content_l2 = ""
            node.properties = {}
            if hasattr(vector_store, "remove"):
                vector_store.remove(node_id)
            if hasattr(graph_store, "remove_entity_edges"):
                graph_store.remove_entity_edges(node_id)
            elif hasattr(graph_store, "graph") and graph_store.graph.has_node(node_id):
                graph_store.graph.remove_edges_from(list(graph_store.graph.in_edges(node_id)) + list(graph_store.graph.out_edges(node_id)))
            if filesystem_store is not None and hasattr(filesystem_store, "delete_entity"):
                filesystem_store.delete_entity(node_id)
        for cid in invalidated:
            child = graph_store.get_node(cid)
            if child:
                child.content = ""
                child.summary_l0 = ""
                child.summary_l1 = ""
                child.content_l2 = ""
                child.properties = {}
                if hasattr(vector_store, "remove"):
                    vector_store.remove(cid)
                if filesystem_store is not None and hasattr(filesystem_store, "delete_entity"):
                    filesystem_store.delete_entity(cid)
        # Persist graph state so deletion_state survives restart
        persistence_error = None
        if hasattr(graph_store, "persist"):
            try:
                graph_store.persist()
            except Exception as e:
                persistence_error = str(e)
        elif hasattr(graph_store, "save"):
            try:
                graph_store.save()
            except Exception as e:
                persistence_error = str(e)
        if persistence_error:
            levels[0].status = "partial"
            levels[0].details += f" Graph persistence failed: {persistence_error}"
            hash_chain.append("deletion_persistence_failed", node_id, {"error": persistence_error}, actor="agent", reason="erasure_request")
            report.verdict = "failed"
        return report
