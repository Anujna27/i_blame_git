from core.erasure_engine import ErasureEngine
from core.erasure_recovery import ErasureRecovery
from core.hash_chain import HashChain
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode
from stores.filesystem_memory import FilesystemMemory
from stores.vector_store import VectorStore


def test_recovery_finishes_interrupted_active_deletion(tmp_path):
    graph = KnowledgeGraph(str(tmp_path / "graph.json"))
    vectors = VectorStore("recovery", str(tmp_path / "vectors"))
    fs = FilesystemMemory(str(tmp_path / "fs"))
    chain = HashChain(str(tmp_path / "audit.json"))
    engine = ErasureEngine(str(tmp_path / "blocked.json"), str(tmp_path / "journal.json"))
    node = MemoryNode(content="recover me", source={"session_id": "s"})
    graph.add_node(node); vectors.add(node); fs.write_entity(node)
    operation_id = engine.journal.begin(node.node_id, "privacy-service", "recovery test")
    engine.journal.advance(operation_id, "mutating")

    result = ErasureRecovery(engine).reconcile(vectors, graph, chain, fs)

    assert result[0]["status"] == "recovered"
    assert graph.get_node(node.node_id).deletion_state != "active"
    assert vectors.get_by_id(node.node_id) is None
    assert fs.read_entity(node.node_id) is None
    assert engine.journal.pending() == []


def test_recovery_verifies_already_completed_mutations(tmp_path):
    graph = KnowledgeGraph(str(tmp_path / "graph.json"))
    vectors = VectorStore("verified_recovery", str(tmp_path / "vectors"))
    chain = HashChain(str(tmp_path / "audit.json"))
    engine = ErasureEngine(str(tmp_path / "blocked.json"), str(tmp_path / "journal.json"))
    node = MemoryNode(content="already handled", source={"session_id": "s"})
    node.transition("source_removed", "privacy-service", "test")
    graph.add_node(node)
    operation_id = engine.journal.begin(node.node_id, "privacy-service", "test")
    engine.blocked_ids.add(node.node_id)
    engine._save_blocked_set()

    result = ErasureRecovery(engine).reconcile(vectors, graph, chain)

    assert result[0]["status"] == "recovered"
    assert engine.journal.pending() == []
