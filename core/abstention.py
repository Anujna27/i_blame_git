# STUB — waiting for M1/M2/M3
class AbstentionEngine:
    def should_abstain(self, query, retrieved_nodes, min_similarity=0.6):
        if any(n.trust_status == "planted" for n in retrieved_nodes): return True, "Retrieved memory is flagged as planted; abstaining."
        if not retrieved_nodes: return True, "No sufficiently relevant memory found."
        return False, ""
