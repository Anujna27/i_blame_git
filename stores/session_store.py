from collections import defaultdict


class SessionStore:
    """Session-scoped aggregate: all entities for a session live behind one boundary."""
    def __init__(self):
        self._entities = defaultdict(dict)

    def add(self, node):
        session_id = node.source.get("session_id", "default")
        self._entities[session_id][node.node_id] = node

    def get(self, session_id):
        return list(self._entities.get(session_id, {}).values())

    def sessions(self):
        return {sid: list(nodes.values()) for sid, nodes in self._entities.items()}

    def all(self):
        return [node for nodes in self._entities.values() for node in nodes.values()]

    def remove(self, node_id, actor="system", reason=""):
        for nodes in self._entities.values():
            node = nodes.get(node_id)
            if node:
                node.transition("source_removed", actor, reason)
                return node
        return None
