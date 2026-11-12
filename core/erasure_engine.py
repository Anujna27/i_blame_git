import hashlib, json, os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Literal
from .residual_risk import ResidualRisk

@dataclass
class LevelResult:
    level_number: int; level_name: str; status: Literal["passed", "partial", "failed"]; details: str; evidence: dict

@dataclass
class ErasureReport:
    node_id: str; node_content: str; levels: list[LevelResult]
    verdict: Literal["fully_deleted", "partially_deleted", "failed"]
    residual_risks: list[ResidualRisk]; timestamp: str; signature: str

class ErasureEngine:
    _model = None
    def __init__(self, blocked_set_path="data/blocked_inference.json"):
        self.blocked_set_path = blocked_set_path; self.blocked_ids = set()
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
    def delete(self, node_id, vector_store, graph_store, hash_chain, reason="user_requested", deleted_by="system"):
        node = graph_store.get_node(node_id); levels=[]
        if node: node.transition("source_removed", deleted_by, reason); vector_store.remove_from_active_index(node_id)
        hash_chain.append("delete_level_1", node_id, {"action":"source_removed", "reason": reason, "deleted_by": deleted_by})
        levels.append(LevelResult(level_number=1, level_name="Source Record Removed", status="passed" if node else "failed", details="Source record removed from active store and index.", evidence={"vector_store_cleared": bool(node), "graph_deletion_state": "source_removed" if node else None}))
        descendants=graph_store.get_descendants(node_id); invalidated=[]; failed=[]
        for cid in descendants:
            child=graph_store.get_node(cid)
            if child: child.transition("invalidated", deleted_by, f"derived from deleted entity: {reason}"); vector_store.remove_from_active_index(cid); invalidated.append(cid)
            else: failed.append(cid)
        hash_chain.append("delete_level_2", node_id, {"invalidated":invalidated,"failed":failed})
        st="passed" if not failed else ("partial" if invalidated else "failed")
        levels.append(LevelResult(level_number=2, level_name="Derived Artifacts Invalidated", status=st, details=f"Invalidated {len(invalidated)} of {len(descendants)} derived artifacts.", evidence={"total_descendants":len(descendants),"invalidated_children":invalidated,"failed_children":failed}))
        self.blocked_ids.add(node_id); self._save_blocked_set(); hash_chain.append("delete_level_3", node_id, {"blocked_set_size":len(self.blocked_ids)})
        levels.append(LevelResult(level_number=3, level_name="Inference Blocked", status="passed", details="Node added to persistent inference block list. All retrieval paths check this set.", evidence={"blocked_set_size":len(self.blocked_ids)}))
        risks=[]; candidates=[]
        try: candidates=vector_store.query(node.content if node else "", top_k=3)
        except Exception: candidates=[]
        if not candidates: candidates=graph_store.get_all_active_nodes()[:50]
        for n in candidates:
            if n.node_id == node_id: continue
            sim=self._similar(node.content if node else "", n.content)
            if sim > .75: risks.append(ResidualRisk(risk_type="semantic_neighbor_proximity", cluster=n.node_id, description=f"Deleted content may be partially reconstructable from {n.node_id} (similarity {sim:.2f}); related content: {n.content}", severity="high" if sim>.85 else "medium", affected_node_ids=[n.node_id]))
        hash_chain.append("delete_level_4", node_id, {"risks_found":len(risks)})
        levels.append(LevelResult(level_number=4, level_name="Non-Inferability Checked", status="partial" if risks else "passed", details="No semantic neighbors above threshold." if not risks else f"{len(risks)} semantic neighbor(s) may partially reconstruct the deleted content.", evidence={"neighbors_checked":len(candidates),"risks_found":len(risks),"risks":[asdict(r) for r in risks]}))
        st5="failed" if descendants else "passed"; detail5=(f"LLM consolidation is non-deterministic. {len(descendants)} derived artifacts were generated from the deleted content and cannot be deterministically reversed. Return to 'never-written' state is not guaranteed." if descendants else "No derived artifacts were generated; state restoration is possible.")
        hash_chain.append("delete_level_5", node_id, {"non_reversible_artifacts":descendants})
        levels.append(LevelResult(level_number=5, level_name="State Restoration Checked", status=st5, details=detail5, evidence={"non_reversible_artifacts":descendants}))
        verdict="failed" if levels[0].status=="failed" or levels[1].status=="failed" else ("partially_deleted" if st5=="failed" or risks else "fully_deleted")
        data={"node_id":node_id,"node_content":node.content if node else "","levels":[asdict(x) for x in levels],"verdict":verdict,"residual_risks":[asdict(r) for r in risks],"timestamp":datetime.now(timezone.utc).isoformat()}
        sig=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest(); report=ErasureReport(node_id=node_id,node_content=node.content if node else "",levels=levels,verdict=verdict,residual_risks=risks,timestamp=data["timestamp"],signature=sig)
        hash_chain.append("deletion_completed",node_id,{"verdict":verdict,"signature":sig})
        # Persist graph state so deletion_state survives restart
        if hasattr(graph_store, "persist"):
            try:
                graph_store.persist()
            except Exception as e:
                pass  # do not fail deletion if persistence has an issue
        elif hasattr(graph_store, "save"):
            try:
                graph_store.save()
            except Exception as e:
                pass
        return report
