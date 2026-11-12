import hashlib
import json


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
    for node in capsule.get("memory_nodes", []):
        if node.get("deletion_state") == "active" and node.get("node_id") in deleted:
            errors.append(f"inconsistent deletion state for node {node.get('node_id')}")
    return len(errors) == 0, errors
