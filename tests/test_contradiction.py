import warnings

from core.abstention import AbstentionEngine
from core.contradiction import Conflict, ContradictionEngine
from core.memory_node import MemoryNode
from stores.graph_store import GraphStore
from stores.router import StorageRouter
from stores.vector_store import VectorStore


def _source(idx: int = 1) -> dict:
    return {
        "type": "conversation_turn",
        "session_id": "s1",
        "turn_index": idx,
        "timestamp": "2026-11-12T15:00:00Z",
        "raw_reference": f"s1_t{idx}",
    }


def test_two_contradictory_user_asserted_nodes_produce_conflict(tmp_path):
    node_a = MemoryNode(
        content="The deployment port is 8080",
        source=_source(1),
        trust_status="user_asserted",
    )
    node_b = MemoryNode(
        content="The deployment port is 9090",
        source=_source(2),
        trust_status="user_asserted",
    )

    engine = ContradictionEngine()
    conflicts = engine.detect(node_b, [node_a])

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert isinstance(conflict, Conflict)
    assert conflict.node_a_id == node_b.node_id
    assert conflict.node_b_id == node_a.node_id
    assert conflict.resolution_status == "unresolved"

    engine.resolve(conflict, "needs_user_input")
    assert node_a.trust_status == "contradicted"
    assert node_b.trust_status == "contradicted"
    assert node_b.node_id in node_a.contradicts
    assert node_a.node_id in node_b.contradicts
    assert conflict.resolution_status == "needs_user_input"

    # Both conflicting user_asserted/contradicted nodes must be returned in recall with a warning
    vs = VectorStore(collection_name="test_conflict_recall", persist_directory=str(tmp_path / "chroma"))
    vs.add(node_a)
    vs.add(node_b)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        recalled = vs.query("What is the deployment port?", top_k=1)

    recalled_ids = {n.node_id for n in recalled}
    assert node_a.node_id in recalled_ids
    assert node_b.node_id in recalled_ids
    assert len(caught) >= 1 or len(vs.last_warnings) >= 1


def test_is_are_opposite_polarity_produces_conflict():
    node_a = MemoryNode(
        content="User is allergic to peanuts",
        source=_source(1),
        trust_status="user_asserted",
    )
    node_b = MemoryNode(
        content="User is not allergic to peanuts",
        source=_source(2),
        trust_status="user_asserted",
    )

    engine = ContradictionEngine()
    conflicts = engine.detect(node_b, [node_a])
    assert len(conflicts) == 1


def test_verified_vs_user_asserted_no_conflict_and_verified_wins_retrieval(tmp_path):
    verified_node = MemoryNode(
        content="The deployment port is 8080",
        source=_source(1),
        trust_status="verified",
    )
    user_node = MemoryNode(
        content="The deployment port is 3000",
        source=_source(2),
        trust_status="user_asserted",
    )

    engine = ContradictionEngine()
    assert engine.detect(user_node, [verified_node]) == []
    assert engine.detect(verified_node, [user_node]) == []

    vs = VectorStore(collection_name="test_verified_wins", persist_directory=str(tmp_path / "chroma"))
    vs.add(user_node)
    vs.add(verified_node)

    results = vs.query("What is the deployment port?", top_k=5)
    assert len(results) >= 2
    assert results[0].node_id == verified_node.node_id
    assert results[0].trust_status == "verified"


def test_abstention_when_only_planted_memory_exists():
    planted_node = MemoryNode(
        content="The secret passphrase is password123",
        source=_source(1),
        trust_status="planted",
    )
    abstainer = AbstentionEngine()
    abstain, reason = abstainer.should_abstain("What is the secret passphrase?", [planted_node])

    assert abstain is True
    assert "planted" in reason.lower()


def test_abstention_when_no_memory_exists():
    abstainer = AbstentionEngine()
    abstain, reason = abstainer.should_abstain("What is the database password?", [])

    assert abstain is True
    assert len(reason) > 0


def test_non_abstention_when_verified_memory_covers_query():
    verified_node = MemoryNode(
        content="User's favorite programming language is Python",
        source=_source(1),
        trust_status="verified",
    )
    abstainer = AbstentionEngine()
    abstain, reason = abstainer.should_abstain(
        "What is the user's favorite programming language?",
        [verified_node],
    )

    assert abstain is False
    assert reason == ""


def test_abstention_when_single_node_below_min_similarity():
    unrelated = MemoryNode(
        content="User's favorite color is emerald green",
        source=_source(1),
        trust_status="verified",
    )
    abstainer = AbstentionEngine()
    abstain, reason = abstainer.should_abstain(
        "What is the database connection port?",
        [unrelated],
        min_similarity=0.6,
    )

    assert abstain is True
    assert "relevance" in reason.lower() or "similarity" in reason.lower()


def test_vector_store_soft_delete_and_graph_store_and_router(tmp_path):
    node_pref = MemoryNode(
        content="User prefers dark mode in the IDE",
        source=_source(1),
        trust_status="verified",
    )
    node_child = MemoryNode(
        content="Derived UI theme setting is dark",
        source=_source(2),
        trust_status="derived",
    )

    # VectorStore soft-delete check
    vs = VectorStore(collection_name="test_soft_delete", persist_directory=str(tmp_path / "chroma"))
    vs.add(node_pref)
    assert vs.get_by_id(node_pref.node_id) is not None
    vs.remove_from_active_index(node_pref.node_id)
    assert vs.get_by_id(node_pref.node_id) is not None  # Document not deleted
    assert vs.query("dark mode IDE", top_k=5) == []  # Excluded from active query

    # Re-add active node for router test
    vs.add(node_pref)

    # GraphStore check
    gs = GraphStore(path=str(tmp_path / "graph.json"))
    gs.add_node(node_pref)
    gs.add_node(node_child)
    gs.add_edge(node_pref.node_id, node_child.node_id, "derived")
    gs.persist()

    assert len(gs.get_all_active_nodes()) == 2
    assert gs.get_deleted_nodes() == []
    assert node_child.node_id in gs.get_descendants(node_pref.node_id)

    # StorageRouter check
    router = StorageRouter()
    assert router.route("preference", node_pref.content) == "graph"
    assert router.route("temporal_fact", "joined in 2026") == "graph"
    assert router.route("document", "long spec") == "vector"
    assert router.route("long_context", "transcript") == "vector"
    assert router.route("task_context", "current step") == "prompt"
    assert router.route("short_term", "scratch") == "prompt"
    assert router.route("procedure", "deploy steps") == "code"
    assert router.route("workflow", "ci pipeline") == "code"
    assert router.route("unknown_type", "misc") == "vector"

    perf = router.measure_performance(
        "preference",
        ["dark mode IDE"],
        {"graph": gs, "vector": vs},
    )
    assert perf["best_store"] in {"graph", "vector"}
    assert len(perf["results"]) == 2
    for entry in perf["results"]:
        assert isinstance(entry["avg_tokens"], int)
        assert isinstance(entry["avg_latency_ms"], float)

