from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path


class SessionStore:
    """Durable session metadata and entity aggregate."""
    def __init__(self, path="data/sessions.json"):
        self.path = Path(path); self._entities = defaultdict(dict); self._sessions = {}; self._load()
    def add(self, node):
        sid = node.source.get("session_id", "default"); self._entities[sid][node.node_id] = node
        self.save_session(sid, entity_ids=self._entities[sid])
    def get(self, session_id): return list(self._entities.get(session_id, {}).values())
    def sessions(self): return {sid: list(nodes.values()) for sid, nodes in self._entities.items()}
    def all(self): return [n for nodes in self._entities.values() for n in nodes.values()]
    def save_session(self, session_id, status="active", committed_at=None, committed_by=None, entity_ids=None):
        ids = [getattr(item, "node_id", item) for item in (entity_ids or [])]
        record = {"session_id": session_id, "status": status, "committed_at": committed_at,
                  "committed_by": committed_by, "entity_ids": ids}
        self._sessions[session_id] = record; self._persist(); return dict(record)
    def get_session(self, session_id):
        record = self._sessions.get(session_id); return dict(record) if record else None
    def commit(self, session_id, actor="harness", reason="session_end"):
        event = self.commit_session(session_id, list(self._entities.get(session_id, {})), actor)
        event["reason"] = reason; self._sessions[session_id]["reason"] = reason; self._persist(); return event
    def commit_session(self, session_id, entity_ids, actor="harness"):
        return self.save_session(session_id, "committed", datetime.now(timezone.utc).isoformat(), actor, entity_ids)
    def last_commit(self, session_id):
        record = self._sessions.get(session_id); return record if record and record.get("status") == "committed" else None
    def remove(self, node_id, actor="system", reason=""):
        for nodes in self._entities.values():
            if node_id in nodes:
                node = nodes[node_id]; node.transition("source_removed", actor, reason); self._persist(); return node
        return None
    def _persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True); self.path.write_text(json.dumps(self._sessions, indent=2), encoding="utf-8")
    def _load(self):
        if not self.path.exists(): return
        payload = json.loads(self.path.read_text(encoding="utf-8")); records = payload.get("sessions", payload)
        self._sessions = {sid: dict(record) for sid, record in records.items() if isinstance(record, dict) and "entity_ids" in record}
