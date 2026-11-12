from datetime import datetime, timezone
import math

from core.active_context import ActiveContext
from core.contradiction import embed_text


TRUST_SCORE = {"verified": 1.0, "user_asserted": 0.7, "derived": 0.5,
               "contradicted": 0.2, "planted": 0.0}


class ContextBuilder:
    """Build bounded harness context from vector and graph evidence."""
    def __init__(self, vector_store, graph, sessions=None, weights=None):
        self.vector_store = vector_store
        self.graph = graph
        self.sessions = sessions
        self.weights = {"vector": .55, "graph": .20, "session": .10,
                        "trust": .10, "recency": .05}
        if weights:
            self.weights.update(weights)

    @staticmethod
    def _cosine(left, right):
        dot = sum(a * b for a, b in zip(left, right))
        ln = math.sqrt(sum(a * a for a in left)); rn = math.sqrt(sum(b * b for b in right))
        return dot / (ln * rn) if ln and rn else 0.0

    def build(self, query, token_budget=2000, session_id=None, blocked_ids=None, top_k=5):
        blocked_ids = set(blocked_ids or [])
        query_vec = embed_text(query)
        vector_hits = self.vector_store.query(query, top_k=top_k)
        vector_scores = {n.node_id: max(0.0, self._cosine(query_vec, embed_text(n.content)))
                         for n in vector_hits}
        candidate_ids = set(vector_scores)
        graph_scores = {}
        for hit in vector_hits:
            for node_id in self.graph.get_ancestors(hit.node_id) + self.graph.get_descendants(hit.node_id):
                candidate_ids.add(node_id)
                try:
                    distance = len(__import__('networkx').shortest_path(self.graph.graph, hit.node_id, node_id)) - 1
                except Exception:
                    distance = 3
                graph_scores[node_id] = max(graph_scores.get(node_id, 0.0),
                                            {1: 1.0, 2: 0.7, 3: 0.4}.get(distance, 0.2))
        ranked = []
        for node_id in candidate_ids:
            node = self.graph.get_node(node_id)
            if not node or node.deletion_state != "active" or node_id in blocked_ids:
                continue
            session_score = 1.0 if session_id and node.source.get("session_id") == session_id else 0.0
            age_days = max(0.0, (datetime.now(timezone.utc) - node.created_at).total_seconds() / 86400)
            recency_score = 1.0 / (1.0 + age_days)
            vector_score = vector_scores.get(node_id, 0.0)
            graph_score = graph_scores.get(node_id, 0.0)
            trust_score = TRUST_SCORE.get(node.trust_status, 0.3)
            final = (self.weights["vector"] * vector_score + self.weights["graph"] * graph_score +
                     self.weights["session"] * session_score + self.weights["trust"] * trust_score +
                     self.weights["recency"] * recency_score)
            ranked.append((final, node, {"vector_score": vector_score, "graph_score": graph_score,
                           "session_score": session_score, "trust_score": trust_score,
                           "recency_score": recency_score, "final_score": final}))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected, tokens, explanations = [], 0, {}
        for _, node, explanation in ranked:
            cost = len(node.content.split())
            if tokens + cost > token_budget: continue
            selected.append(node); tokens += cost; explanations[node.node_id] = explanation
        vector_ids = [n.node_id for n in selected if n.node_id in vector_scores]
        graph_ids = [n.node_id for n in selected if n.node_id in graph_scores and n.node_id not in vector_scores]
        session_ids = [n.node_id for n in selected if session_id and n.source.get("session_id") == session_id]
        return ActiveContext(query, selected, tokens, vector_ids, graph_ids, session_ids,
                             explanations, list(getattr(self.vector_store, "last_warnings", [])))
