import pytest
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from core.memory_node import MemoryNode
from core.hash_chain import HashChain
from core.erasure_engine import ErasureEngine
from core.residual_risk import ResidualRiskReporter

def _source(idx=1):
    return {"type": "conversation_turn", "session_id": "s1", "turn_index": idx,
            "timestamp": "2026-11-12T00:00:00Z", "raw_reference": f"s1_t{idx}"}

def test_delete_missing_node():
    class MockGraph:
        def get_node(self, node_id): return None
        def get_descendants(self, node_id): return []
        def get_all_active_nodes(self): return []
    class MockVec:
        def remove_from_active_index(self, node_id): pass
        def query(self, q, top_k=3): return []
    report = ErasureEngine("data/_test_blocked_missing.json").delete("nonexistent-id", MockVec(), MockGraph(), HashChain("data/_test_audit_missing.json"))
    assert report is not None; assert report.levels[0].status == "failed"; assert report.verdict == "failed"

def test_delete_leaf_node():
    node = MemoryNode(content="Leaf node fact", source=_source(), trust_status="user_asserted")
    class MockGraph:
        def get_node(self, node_id): return node
        def get_descendants(self, node_id): return []
        def get_all_active_nodes(self): return [node]
    class MockVec:
        def remove_from_active_index(self, node_id): pass
        def query(self, q, top_k=3): return []
    report = ErasureEngine("data/_test_blocked_leaf.json").delete(node.node_id, MockVec(), MockGraph(), HashChain("data/_test_audit_leaf.json"))
    assert report.levels[0].status == "passed"; assert report.levels[1].status == "passed"; assert report.levels[4].status == "passed"; assert report.verdict == "fully_deleted"

def test_notice_for_fully_deleted():
    node = MemoryNode(content="Simple fact", source=_source(), trust_status="user_asserted")
    class MockGraph:
        def get_node(self, node_id): return node
        def get_descendants(self, node_id): return []
        def get_all_active_nodes(self): return [node]
    class MockVec:
        def remove_from_active_index(self, node_id): pass
        def query(self, q, top_k=3): return []
    report = ErasureEngine("data/_test_blocked_notice.json").delete(node.node_id, MockVec(), MockGraph(), HashChain("data/_test_audit_notice.json"))
    notice = ResidualRiskReporter().generate_notice(report)
    assert "FULLY DELETED" in notice; assert "none" in notice.lower(); print("\n" + notice)

def test_partially_deleted_notice_with_real_risk(tmp_path):
    parent = MemoryNode(content="User's API key is sk-abc123", source=_source())
    child_source = {**_source(), "type": "derived", "raw_reference": parent.node_id}
    children = [
        MemoryNode(content="Summary: user's key starts with sk-", source=child_source),
        MemoryNode(content="Embedding: API credential information", source=child_source),
        MemoryNode(content="Code: config = {'key': 'sk-abc123'}", source=child_source),
    ]
    class MockGraph:
        def __init__(self): self.nodes = {n.node_id: n for n in [parent, *children]}
        def get_node(self, node_id): return self.nodes.get(node_id)
        def get_descendants(self, node_id): return [n.node_id for n in children] if node_id == parent.node_id else []
        def get_all_active_nodes(self): return [n for n in self.nodes.values() if n.deletion_state == "active"]
    neighbors = [
        MemoryNode(content="API credentials are important", source=_source(2)),
        MemoryNode(content="The user's key begins with sk-", source=_source(3)),
        MemoryNode(content="Config file contains secrets", source=_source(4)),
    ]
    class MockVectorStore:
        def remove_from_active_index(self, node_id): pass
        def query(self, query_text, top_k=3): return neighbors[:top_k]
    report = ErasureEngine(str(tmp_path / "blocked.json")).delete(
        parent.node_id, MockVectorStore(), MockGraph(), HashChain(str(tmp_path / "audit.json")))
    assert len(report.levels) == 5
    assert report.levels[0].status == "passed"
    assert report.levels[1].status == "passed"
    assert report.levels[2].status == "passed"
    assert report.levels[3].status == "partial"
    assert report.levels[4].status == "failed"
    assert report.verdict == "partially_deleted"
    assert len(report.residual_risks) >= 1
    assert any("sk-" in risk.description or "key" in risk.description.lower() for risk in report.residual_risks)
    notice = ResidualRiskReporter().generate_notice(report)
    print("\n===== PARTIALLY DELETED NOTICE (demo scenario) =====\n")
    print(notice)
