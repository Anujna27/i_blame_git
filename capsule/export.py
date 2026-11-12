import json
import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class CapsuleExporter:
    def export(self, agent_name, all_nodes, provenance_graph, hash_chain, residual_risks, session_commits=None):
        capsule_id = str(uuid4())
        lifecycle_history = {n.node_id: list(getattr(n, "lifecycle", [])) for n in all_nodes}
        edges = [{"parent": u, "child": v, "type": d.get("type", d.get("edge_type", "derived")), "metadata": dict(d)} for u, v, d in provenance_graph.graph.edges(data=True)]
        capsule = {
            "@context": "https://mnemosyne.dev/schema/v1",
            "capsule_id": capsule_id,
            "exported_at": datetime.now(timezone.utc).isoformat() + "Z",
            "source_agent": agent_name,
            "memory_nodes": [n.to_jsonld() for n in all_nodes],
            "entities": [n.to_jsonld() for n in all_nodes],
            "lifecycle_history": lifecycle_history,
            "derivation_graph": {"nodes": list(provenance_graph.graph.nodes), "edges": edges},
            "session_commits": session_commits if session_commits is not None else getattr(provenance_graph, "session_commits", {}),
            "deletion_audit": {
                "deleted_nodes": [n.node_id for n in all_nodes if n.deletion_state != "active"],
                "invalidated_children": [n.node_id for n in all_nodes if n.deletion_state == "invalidated"],
                "entries": [{"entity_id": n.node_id, "entity_type": n.entity_type,
                             "deleted_by": n.deleted_by,
                             "deleted_at": n.deleted_at.isoformat() if n.deleted_at else None,
                             "reason": n.deleted_reason,
                             "verdict": "partially_deleted" if n.deletion_state == "invalidated" else "fully_deleted"}
                            for n in all_nodes if n.deletion_state != "active"],
                "residual_risk_flags": [dataclasses.asdict(r) for r in residual_risks],
            },
            "hash_chain": {"entries": hash_chain.get_entries(), "integrity_verified": hash_chain.verify_integrity()[0]},
            "retrieval_hints": {"token_budget_default": 2000, "preferred_stores": {"preferences": "graph", "documents": "vector", "task_context": "prompt", "procedures": "code"}},
        }
        output_dir = Path("data") / "capsules"
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / f"cap_{capsule_id}.json").open("w", encoding="utf-8") as f:
            json.dump(capsule, f, indent=2)
        return capsule
