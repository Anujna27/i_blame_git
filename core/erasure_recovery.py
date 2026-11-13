"""Recovery and verification for interrupted erasure operations."""


class ErasureRecovery:
    def __init__(self, engine):
        self.engine = engine

    def reconcile(self, vector_store, graph_store, hash_chain, filesystem_store=None):
        results = []
        for entry in self.engine.journal.pending():
            entity_id = entry["entity_id"]
            node = graph_store.get_node(entity_id)
            try:
                if node is not None and node.deletion_state == "active":
                    report = self.engine.delete(
                        entity_id,
                        vector_store,
                        graph_store,
                        hash_chain,
                        reason=entry.get("reason", "recovered erasure"),
                        deleted_by=entry.get("actor", "recovery-service"),
                        filesystem_store=filesystem_store,
                    )
                    self.engine.journal.complete(entry["operation_id"], "recovered")
                    results.append({"operation_id": entry["operation_id"], "entity_id": entity_id, "status": "recovered", "verdict": report.verdict})
                    continue

                checks = {
                    "graph_non_active": bool(node is not None and node.deletion_state != "active"),
                    "vector_absent": vector_store.get_by_id(entity_id) is None,
                    "filesystem_absent": filesystem_store is None or filesystem_store.read_entity(entity_id) is None,
                    "inference_blocked": entity_id in self.engine.blocked_ids,
                }
                if all(checks.values()):
                    self.engine.journal.complete(entry["operation_id"], "recovered")
                    results.append({"operation_id": entry["operation_id"], "entity_id": entity_id, "status": "recovered", "checks": checks})
                else:
                    self.engine.journal.advance(entry["operation_id"], "failed", {"checks": checks})
                    results.append({"operation_id": entry["operation_id"], "entity_id": entity_id, "status": "failed", "checks": checks})
            except Exception as error:
                self.engine.journal.advance(entry["operation_id"], "failed", {"error": str(error)})
                results.append({"operation_id": entry["operation_id"], "entity_id": entity_id, "status": "failed", "error": str(error)})
        return results
