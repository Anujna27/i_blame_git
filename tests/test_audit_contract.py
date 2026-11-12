from datetime import datetime, timezone

from core.hash_chain import HashChain
from core.memory_node import MemoryNode


def test_audit_event_has_accountability_fields(tmp_path):
    chain = HashChain(str(tmp_path / "audit.json"))
    node = MemoryNode(content="temporary fact", source={"type": "test", "session_id": "s1", "turn_index": 0, "timestamp": datetime.now(timezone.utc).isoformat(), "raw_reference": "test"})
    entry = chain.append("entity_deleted", node.node_id, {"preview": node.content}, actor="user", reason="user_requested_erasure", metadata={"entity_type": "memory"})
    assert entry["entity_id"] == node.node_id
    assert entry["actor"] == "user"
    assert entry["reason"] == "user_requested_erasure"
    assert entry["metadata"]["entity_type"] == "memory"
    assert entry["timestamp"]
    assert chain.verify_integrity() == (True, [])
