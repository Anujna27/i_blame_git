from core.context_builder import ContextBuilder
from core.memory_node import MemoryNode
from core.provenance_graph import ProvenanceGraph


class FakeVector:
    def __init__(self, hits):
        self.hits = hits
        self.last_warnings = ["contradiction warning"]

    def query(self, query, top_k=5):
        return self.hits[:top_k]


def node(text, session="s1", trust="user_asserted"):
    return MemoryNode(content=text, trust_status=trust,
                      source={"session_id": session})


def test_hybrid_context_expands_graph_and_exposes_sources(tmp_path):
    hit = node("User prefers Python", "s1", "verified")
    related = node("Python is used for the deployment service", "s2")
    graph = ProvenanceGraph(str(tmp_path / "graph.json"))
    graph.add_node(hit)
    graph.add_node(related)
    graph.add_edge(hit.node_id, related.node_id, "RELATED_TO")

    context = ContextBuilder(FakeVector([hit]), graph).build("preferred language")

    assert hit.node_id in context.vector_entity_ids
    assert related.node_id in context.graph_entity_ids
    assert context.warnings == ["contradiction warning"]
    assert related in context.entities


def test_context_filters_deleted_and_respects_budget(tmp_path):
    active = node("active entity with several words", "s1")
    deleted = node("deleted entity must not appear", "s1")
    deleted.transition("source_removed", "user", "erasure")
    graph = ProvenanceGraph(str(tmp_path / "graph.json"))
    graph.add_node(active)
    graph.add_node(deleted)

    context = ContextBuilder(FakeVector([active, deleted]), graph).build("entity", token_budget=2)

    assert deleted not in context.entities
    assert context.token_count <= 2


def test_session_relevance_is_explained(tmp_path):
    current = node("shared preference", "current")
    other = node("shared preference", "other")
    graph = ProvenanceGraph(str(tmp_path / "graph.json"))
    graph.add_node(current)
    graph.add_node(other)
    context = ContextBuilder(FakeVector([current, other]), graph).build(
        "shared preference", session_id="current")

    assert context.ranking_explanations[current.node_id]["session_score"] == 1.0
    assert context.session_entity_ids == [current.node_id]
