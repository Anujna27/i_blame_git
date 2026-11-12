import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from demo.demo_runner import load_notice_snapshot, save_notice_snapshot

SOURCE = {"type": "conversation_turn", "session_id": "demo", "turn_index": 1,
          "timestamp": "2026-11-12T00:00:00Z", "raw_reference": "demo_t1"}

parent = MemoryNode(content="User's API key is sk-abc123", source=SOURCE)
children = [MemoryNode(content=text, source={**SOURCE, "type": "derived", "raw_reference": parent.node_id}) for text in (
    "Summary: user's key starts with sk-",
    "Embedding: API credential information",
    "Code: config = {'key': 'sk-abc123'}",
)]

class MockGraphStore:
    def __init__(self): self.nodes = {n.node_id: n for n in [parent, *children]}
    def get_node(self, node_id): return self.nodes.get(node_id)
    def get_descendants(self, node_id): return [n.node_id for n in children] if node_id == parent.node_id else []
    def get_all_active_nodes(self): return [n for n in self.nodes.values() if n.deletion_state == "active"]

class MockVectorStore:
    def remove_from_active_index(self, node_id): pass
    def query(self, query_text, top_k=3): return [MemoryNode(content="The user's API key is sk-abc123", source=SOURCE)][:top_k]

report = ErasureEngine("data/demo_blocked.json").delete(parent.node_id, MockVectorStore(), MockGraphStore(), HashChain("data/demo_audit.json"))
save_notice_snapshot(report)
print("Snapshot saved to data/demo_notice_snapshot.json")
print(load_notice_snapshot())
