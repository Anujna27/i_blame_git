"""Durable journal for multi-store deletion recovery and verification."""

import json
import os
import threading
import uuid
from datetime import datetime, timezone


class ErasureJournal:
    def __init__(self, path="data/erasure_journal.json"):
        self.path = path
        self._lock = threading.RLock()
        self.entries = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                self.entries = json.load(handle)

    def _persist(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(self.entries, handle, indent=2)
        os.replace(temp, self.path)

    def begin(self, entity_id, actor, reason):
        with self._lock:
            entry = {
                "operation_id": str(uuid.uuid4()),
                "entity_id": entity_id,
                "actor": actor,
                "reason": reason,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "phase": "started",
                "completed": False,
            }
            self.entries.append(entry)
            self._persist()
            return entry["operation_id"]

    def advance(self, operation_id, phase, details=None):
        with self._lock:
            entry = self._find(operation_id)
            if entry is None:
                raise KeyError(operation_id)
            entry["phase"] = phase
            if details:
                entry.setdefault("phases", {})[phase] = details
            self._persist()

    def complete(self, operation_id, verdict):
        with self._lock:
            entry = self._find(operation_id)
            if entry is None:
                raise KeyError(operation_id)
            entry.update({
                "phase": "completed",
                "completed": True,
                "verdict": verdict,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            self._persist()

    def pending(self):
        with self._lock:
            return [dict(entry) for entry in self.entries if not entry.get("completed")]

    def _find(self, operation_id):
        return next((entry for entry in self.entries if entry.get("operation_id") == operation_id), None)
