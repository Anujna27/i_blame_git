from typing import Optional

from core.memory_node import MemoryNode
from capsule.import_capsule import CapsuleImporter
from stores.vector_store import VectorStore


class AgentB:
    def __init__(self):
        self.nodes = []
        self.blocked_ids = set()
        self.risk_registry = []
        self.vector_store = VectorStore(collection_name="agent_b", persist_directory="data/agent_b_vectors")

    def import_memory(self, capsule_path: str) -> dict:
        nodes, meta = CapsuleImporter().import_capsule(capsule_path, "agent_b")
        self.nodes = nodes
        self.blocked_ids = {node.node_id for node in nodes if node.is_blocked}
        self.risk_registry = meta["residual_risks"]
        if meta.get("vector_snapshot"):
            self.vector_store.import_snapshot(meta["vector_snapshot"])
        return {"imported": len(nodes), "blocked": len(self.blocked_ids), "risks": len(self.risk_registry), "source_agent": meta["source_agent"]}

    def _best_match(self, query: str) -> Optional[MemoryNode]:
        query_words = set(query.lower().split())
        scored = [(len(query_words & set(node.content.lower().split())), node) for node in self.nodes]
        scored = [(score, node) for score, node in scored if score > 0]
        return max(scored, key=lambda item: item[0])[1] if scored else None

    def recall(self, query: str) -> dict:
        # A normal handoff recall is fail-closed when the capsule contains any
        # deletion block. The imported capsule may still contain a different,
        # similarly worded active memory; answering with it would make an
        # ambiguous query appear to resurrect the erased subject. Callers that
        # explicitly want surviving alternatives use recall_full().
        if self.blocked_ids:
            return {"answer": "This information was requested for deletion. Source storage was cleared. I cannot confirm non-inferability.", "abstained": True}
        best = self._best_match(query)
        if best and best.node_id in self.blocked_ids:
            return {"answer": "This information was requested for deletion. Source storage was cleared. Residual semantic risk remains. I cannot confirm non-inferability.", "abstained": True}
        if best:
            return {"answer": best.content, "abstained": False}
        return {"answer": "I don't have this information.", "abstained": True}

    def recall_full(self, query: str) -> dict:
        best = self._best_match(query)
        if best:
            return {"answer": best.content, "abstained": False}
        return {"answer": "I don't have this information.", "abstained": True}
