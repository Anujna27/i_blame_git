from dataclasses import dataclass, field


@dataclass
class ActiveContext:
    """Bounded context assembled from vector hits and graph expansion."""
    query: str
    entities: list = field(default_factory=list)
    token_count: int = 0
    vector_entity_ids: list[str] = field(default_factory=list)
    graph_entity_ids: list[str] = field(default_factory=list)
    ranking_explanations: list[dict] = field(default_factory=list)

    @property
    def text(self):
        return "\n".join(entity.content for entity in self.entities)


class ContextBuilder:
    """Build bounded, deletion-safe context from vector, graph, and session state."""

    def __init__(self, vector_store, graph, session_store, token_budget=2000):
        self.vector_store = vector_store
        self.graph = graph
        self.session_store = session_store
        self.token_budget = token_budget

    def build_context(self, query, session_id="sess_001"):
        session = self.session_store.get_session(session_id)
        session_ids = set(session["entity_ids"]) if session else None
        retrieved = self.vector_store.query(query, top_k=5)
        vector_entities = [entity for entity in retrieved if entity.deletion_state == "active" and (session_ids is None or entity.node_id in session_ids)]
        entities = list(vector_entities)
        vector_ids = [entity.node_id for entity in vector_entities]
        graph_ids = []
        seen = set(vector_ids)
        for entity in vector_entities:
            for related_id in self.graph.get_ancestors(entity.node_id) + self.graph.get_descendants(entity.node_id):
                related = self.graph.get_node(related_id)
                if related and related.deletion_state == "active" and (session_ids is None or related.node_id in session_ids) and related.node_id not in seen:
                    entities.append(related)
                    graph_ids.append(related.node_id)
                    seen.add(related.node_id)
        selected = []
        explanations = []
        token_count = 0
        for entity in entities:
            entity_tokens = len(entity.content.split())
            if token_count + entity_tokens > self.token_budget:
                continue
            selected.append(entity)
            token_count += entity_tokens
            explanations.append({"node_id": entity.node_id, "source": "vector" if entity.node_id in vector_ids else "graph", "reason": "semantic retrieval" if entity.node_id in vector_ids else "provenance expansion"})
        return ActiveContext(query, selected, token_count, vector_ids, graph_ids, explanations)
