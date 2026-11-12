import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class CapsuleExporter:
    def export(self, agent_name, all_nodes, provenance_graph, hash_chain, residual_risks):
        capsule_id = str(uuid4())
        capsule = {
            "@context": "https://mnemosyne.dev/schema/v1",
            "capsule_id": capsule_id,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "source_agent": agent_name,
            "memory_nodes": [n.to_jsonld() for n in all_nodes],
            "derivation_graph": {"edges": [{"parent": u, "child": v, "type": d.get("edge_type", "derived")} for u, v, d in provenance_graph.graph.edges(data=True)]},
            "deletion_audit": {
                "deleted_nodes": [n.node_id for n in all_nodes if n.deletion_state != "active"],
                "invalidated_children": [n.node_id for n in all_nodes if n.deletion_state == "invalidated"],
                "residual_risk_flags": [r.model_dump() for r in residual_risks],
            },
            "hash_chain": {"entries": hash_chain.get_entries(), "integrity_verified": hash_chain.verify_integrity()[0]},
            "retrieval_hints": {"token_budget_default": 2000, "preferred_stores": {"preferences": "graph", "documents": "vector", "task_context": "prompt", "procedures": "code"}},
        }
        output_dir = Path("data") / "capsules"
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / f"cap_{capsule_id}.json").open("w", encoding="utf-8") as f:
            json.dump(capsule, f, indent=2)
        return capsule
