import json
from pathlib import Path

from core.memory_node import MemoryNode
from .validator import validate_capsule


class CapsuleImporter:
    def import_capsule(self, path, target_agent):
        with Path(path).open(encoding="utf-8") as f:
            capsule = json.load(f)
        valid, errors = validate_capsule(capsule)
        if not valid:
            raise ValueError(f"Capsule validation failed for target {target_agent}: {errors}")
        deleted = capsule["deletion_audit"]["deleted_nodes"]
        nodes = []
        for node_dict in capsule["memory_nodes"]:
            node = MemoryNode.from_jsonld(node_dict)
            if node.node_id in deleted or node.deletion_state != "active":
                node.is_blocked = True
            nodes.append(node)
        return nodes, {"residual_risks": capsule["deletion_audit"]["residual_risk_flags"], "audit_verified": True, "source_agent": capsule["source_agent"]}
