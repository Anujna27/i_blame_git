from collections import defaultdict
import json
from pathlib import Path


class SessionStore:
    """Durable session aggregate for entity memory and commit metadata."""
    def __init__(self, path="data/sessions.json"):
        self.path = path
        self._entities = defaultdict(dict)
        self._commits = {}
        self._load()

    def add(self, node):
        session_id = node.source.get("session_id", "default")
        self._entities[session_id][node.node_id] = node
        self._persist()

    def get(self, session_id):
        return list(self._entities.get(session_id, {}).values())

    def sessions(self):
        return {sid: list(nodes.values()) for sid, nodes in self._entities.items()}

    def all(self):
        return [node for nodes in self._entities.values() for node in nodes.values()]

    def commit(self, session_id, actor="harness", reason="session_end"):
        from datetime import datetime, timezone
        event = {"session_id": session_id, "actor": actor, "reason": reason,
                 "timestamp": datetime.now(timezone.utc).isoformat(),
                 "entity_ids": list(self._entities.get(session_id, {}))}
        self._commits[session_id] = event
        self._persist()
        return event

    def last_commit(self, session_id):
        return self._commits.get(session_id)

    def remove(self, node_id, actor="system", reason=""):
        for nodes in self._entities.values():
            node = nodes.get(node_id)
            if node:
                node.transition("source_removed", actor, reason)
                self._persist()
                return node
        return None

    def _persist(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        payload = {"sessions": {sid: {nid: node.to_jsonld() for nid, node in nodes.items()}
                                 for sid, nodes in self._entities.items()},
                   "commits": self._commits}
        Path(self.path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self):
        path = Path(self.path)
        if not path.exists():
            return
        from core.memory_node import MemoryNode
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._commits = payload.get("commits", {})
        for sid, nodes in payload.get("sessions", {}).items():
            self._entities[sid] = {nid: MemoryNode.from_jsonld(data) for nid, data in nodes.items()}
