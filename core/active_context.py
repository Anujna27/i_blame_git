from dataclasses import dataclass, field


@dataclass
class ActiveContext:
    """Bounded context assembled from vector hits and graph expansion."""
    query: str
    entities: list = field(default_factory=list)
    token_count: int = 0
    vector_entity_ids: list[str] = field(default_factory=list)
    graph_entity_ids: list[str] = field(default_factory=list)
    session_entity_ids: list[str] = field(default_factory=list)
    ranking_explanations: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self):
        return "\n".join(entity.content for entity in self.entities)
