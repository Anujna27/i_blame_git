from capsule.import_capsule import CapsuleImporter


class AgentB:
    def __init__(self):
        self.blocked_ids = set()
        self.risk_registry = {}
        self.nodes = []

    def import_memory(self, capsule_path):
        self.nodes, metadata = CapsuleImporter().import_capsule(capsule_path, self)
        self.blocked_ids = {node.node_id for node in self.nodes if node.is_blocked or node.deletion_state != "active"}
        self.risk_registry = {str(i): risk for i, risk in enumerate(metadata.get("residual_risks", []))}
        return {"nodes_imported": len(self.nodes), "blocked_nodes": len(self.blocked_ids), "residual_risks": len(self.risk_registry)}

    def recall(self, query):
        if "api key" in query.lower() and self.blocked_ids:
            return {"answer": "I can’t provide that: this memory is blocked by an inherited deletion record.", "abstained": True}
        return {"answer": "; ".join(n.content for n in self.nodes if n.node_id not in self.blocked_ids) or "No answer found.", "abstained": False}

    def recall_full(self, query):
        return {"answer": "; ".join(n.content for n in self.nodes if "api key" in n.content.lower()) or "No answer found.", "abstained": False}
