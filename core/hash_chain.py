import hashlib
import json
import os
import uuid
import threading
from datetime import datetime, timezone


class HashChain:
    _write_lock = threading.RLock()
    def __init__(self, log_path: str = "data/audit_log.json"):
        self.log_path = log_path
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as f:
                self.entries = json.load(f)
        else:
            self.entries = []
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    @staticmethod
    def _digest(entry, prev_hash):
        payload = json.dumps(entry, sort_keys=True, separators=(",", ":")) + prev_hash
        return hashlib.sha256(payload.encode()).hexdigest()

    def append(self, operation, node_id, details, actor="system", reason="mutation", metadata=None):
        with self._write_lock:
            event_id = str(uuid.uuid4())
            entry = {"entry_id": event_id, "event_id": event_id, "operation": operation, "node_id": node_id,
                     "entity_id": node_id, "actor": actor or "system", "reason": reason or "mutation",
                     "metadata": metadata or {}, "details": details, "prev_hash": self.get_last_hash(),
                     "timestamp": datetime.now(timezone.utc).isoformat(), "hash": ""}
            entry["hash"] = self._digest({k: v for k, v in entry.items() if k != "hash"}, entry["prev_hash"])
            self.entries.append(entry)
            os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
            tmp_path = self.log_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2)
            os.replace(tmp_path, self.log_path)
            return entry

    def verify_integrity(self):
        errors = []
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i - 1]["hash"] if i else "GENESIS"
            if entry.get("prev_hash") != expected_prev:
                errors.append(f"entry {i}: prev_hash mismatch")
            actual = self._digest({k: v for k, v in entry.items() if k != "hash"}, entry.get("prev_hash", ""))
            if actual != entry.get("hash"):
                errors.append(f"entry {i}: hash mismatch")
        return (not errors, errors)

    def get_entries(self):
        return list(self.entries)

    def get_last_hash(self):
        return self.entries[-1]["hash"] if self.entries else "GENESIS"
