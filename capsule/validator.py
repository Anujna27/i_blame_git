import hashlib
import json
from datetime import datetime


def validate_capsule(capsule):
    errors = []
    for key in ("@context", "capsule_id", "memory_nodes", "deletion_audit", "hash_chain"):
        if key not in capsule:
            errors.append(f"missing key: {key}")
    entries = capsule.get("hash_chain", {}).get("entries", [])
    previous_hash = "GENESIS"
    for entry in entries:
        payload = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True, separators=(",", ":")) + previous_hash
        expected = hashlib.sha256(payload.encode()).hexdigest()
        if entry.get("hash") != expected:
            errors.append(f"hash chain broken at entry {entry.get('entry_id')}")
        previous_hash = entry.get("hash", "")
    deleted = capsule.get("deletion_audit", {}).get("deleted_nodes", [])
    entity_ids = {node.get("node_id") for node in capsule.get("memory_nodes", [])}
    graph = capsule.get("derivation_graph", {})
    if not set(graph.get("nodes", [])).issubset(entity_ids):
        errors.append("graph node references missing entity")
    for edge in graph.get("edges", []):
        if edge.get("parent") not in entity_ids or edge.get("child") not in entity_ids:
            errors.append(f"graph edge references missing entity: {edge}")
    for node in capsule.get("memory_nodes", []):
        if node.get("deletion_state") == "active" and node.get("node_id") in deleted:
            errors.append(f"inconsistent deletion state for node {node.get('node_id')}")
    for node_id, events in capsule.get("lifecycle_history", {}).items():
        if node_id not in entity_ids:
            errors.append(f"lifecycle history references missing entity: {node_id}")
        for event in events:
            for key in ("event_id", "state", "actor", "reason", "timestamp", "metadata"):
                if key not in event:
                    errors.append(f"lifecycle event missing {key}: {node_id}")
            try:
                datetime.fromisoformat(event.get("timestamp", "").replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"invalid lifecycle timestamp: {node_id}")
    for entry in entries:
        if entry.get("operation", "").startswith("delete") or entry.get("operation") == "deletion_completed":
            for key in ("event_id", "actor", "reason", "timestamp", "prev_hash", "hash"):
                if key not in entry:
                    errors.append(f"audit entry missing {key}: {entry.get('entry_id')}")
    for audit in capsule.get("deletion_audit", {}).get("entries", []):
        for key in ("entity_id", "deleted_by", "deleted_at", "reason"):
            if not audit.get(key):
                errors.append(f"deletion audit missing {key}: {audit.get('entity_id')}")
        if audit.get("deleted_at"):
            try:
                datetime.fromisoformat(audit["deleted_at"].replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"invalid deletion audit timestamp: {audit.get('entity_id')}")
    return len(errors) == 0, errors
