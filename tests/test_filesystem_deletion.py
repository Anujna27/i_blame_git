from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode
from stores.filesystem_memory import FilesystemMemory
from stores.vector_store import VectorStore


def test_erasure_removes_filesystem_copies(tmp_path):
    fs = FilesystemMemory(str(tmp_path / "viking"))
    graph = KnowledgeGraph(str(tmp_path / "graph.json"))
    vectors = VectorStore("filesystem_delete", str(tmp_path / "vectors"))
    chain = HashChain(str(tmp_path / "audit.json"))
    engine = ErasureEngine(str(tmp_path / "blocked.json"))

    parent = MemoryNode(content="secret filesystem memory", source={"session_id": "s1"})
    child = MemoryNode(content="derived secret filesystem memory", source={"session_id": "s1"})
    for node in (parent, child):
        graph.add_node(node)
        vectors.add(node)
        fs.write_entity(node)
    graph.add_edge(parent.node_id, child.node_id, "DERIVED_FROM")

    report = engine.delete(
        parent.node_id,
        vectors,
        graph,
        chain,
        filesystem_store=fs,
    )

    assert report.verdict == "partially_deleted"
    assert fs.read_entity(parent.node_id) is None
    assert fs.read_entity(child.node_id) is None
