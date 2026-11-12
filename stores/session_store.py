import json
from datetime import datetime, timezone
from pathlib import Path


class SessionStore:
    """Persistent session metadata store; entity vectors remain in VectorStore."""

    def __init__(self, path="data/sessions.json"):
        self.path = Path(path)
        self._sessions = {}
        self._load()

    def save_session(self, session_id, status="active", committed_at=None,
                     committed_by=None, entity_ids=None):
        record = {
            "session_id": session_id,
            "status": status,
            "committed_at": committed_at,
            "committed_by": committed_by,
            "entity_ids": list(entity_ids or []),
        }
        self._sessions[session_id] = record
        self._persist()
        return dict(record)

    def get_session(self, session_id):
        record = self._sessions.get(session_id)
        return dict(record) if record is not None else None

    def commit_session(self, session_id, entity_ids, actor="harness"):
        return self.save_session(
            session_id=session_id,
            status="committed",
            committed_at=datetime.now(timezone.utc).isoformat(),
            committed_by=actor,
            entity_ids=entity_ids,
        )

    def _persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._sessions, indent=2), encoding="utf-8")

    def _load(self):
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = payload.get("sessions", {}) if isinstance(payload, dict) and "sessions" in payload else payload
        if isinstance(records, dict):
            self._sessions = {
                session_id: dict(record)
                for session_id, record in records.items()
                if isinstance(record, dict) and "entity_ids" in record
            }
