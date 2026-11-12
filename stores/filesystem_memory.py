import json
from pathlib import Path


class FilesystemMemory:
    """Inspectable viking://-style memory backed by ordinary directories."""
    def __init__(self, root="data/viking_memory"):
        self.root = Path(root)

    def _path(self, namespace, entity_id):
        safe = str(entity_id).replace("..", "_").replace("/", "_").replace("\\", "_")
        return self.root / namespace / f"{safe}.json"

    def write_entity(self, entity, namespace="user/memories"):
        path = self._path(namespace, entity.node_id if hasattr(entity, "node_id") else entity["node_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = entity.to_jsonld() if hasattr(entity, "to_jsonld") else dict(entity)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return f"viking://{namespace}/{path.stem}"

    def read_entity(self, entity_id, namespace="user/memories"):
        path = self._path(namespace, entity_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def list_entities(self, namespace="user/memories"):
        directory = self.root / namespace
        return [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")] if directory.exists() else []
