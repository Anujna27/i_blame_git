# STUB — waiting for M1/M2/M3
import json
from core.memory_node import MemoryNode
class CapsuleImporter:
    def import_capsule(self, path, target_agent):
        data=json.load(open(path, encoding="utf-8")); nodes=[MemoryNode.from_dict(x) for x in data.get("memory_nodes", [])]
        return nodes, data.get("deletion_audit", {})
