from core.memory_node import MemoryNode
from core.graph_healer import GraphHealer
from stores.vector_store import VectorStore


def test_vector_snapshot_round_trip(tmp_path):
    first = VectorStore("snapshot_a", str(tmp_path / "a"))
    node = MemoryNode(content="snapshot entity")
    first.add(node)
    snapshot = first.export_snapshot()
    second = VectorStore("snapshot_b", str(tmp_path / "b"))
    second.import_snapshot(snapshot)
    assert second.get_by_id(node.node_id).content == node.content
    assert second.query("snapshot entity", 1)[0].node_id == node.node_id


def test_explicit_duplicate_merge_removes_vector_record(tmp_path):
    from core.knowledge_graph import KnowledgeGraph
    graph = KnowledgeGraph(str(tmp_path / "graph.json"))
    vector = VectorStore("merge", str(tmp_path / "vec"))
    keep = MemoryNode(content="same preference")
    remove = MemoryNode(content="same preference")
    graph.add_node(keep); graph.add_node(remove); vector.add(keep); vector.add(remove)
    result = GraphHealer(graph, vector).merge_duplicate(keep.node_id, remove.node_id)
    assert result["kept_entity"] == keep.node_id
    assert graph.get_entity(remove.node_id)["deletion_state"] == "merged"
    assert vector.get_by_id(remove.node_id) is None
