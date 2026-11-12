import json

from agents import AgentA
from stores.session_store import SessionStore


def test_entity_lifecycle_and_session_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = AgentA()

    node = agent.remember("I prefer tea", session_id="sess_001")
    original_id = node.node_id
    assert node.lifecycle[-1]["state"] == "created"
    assert {"event_id", "state", "actor", "reason", "timestamp", "metadata"} <= set(node.lifecycle[-1])

    updated = agent.update_entity(original_id, "I prefer coffee")
    assert updated.node_id == original_id
    assert updated.version == 2
    assert updated.content == "I prefer coffee"
    assert updated.lifecycle[-1]["state"] == "updated"
    assert updated.lifecycle[-1]["metadata"]["old_content"] == "I prefer tea"
    assert any(entry["operation"] == "entity_created" for entry in agent.hash_chain.get_entries())
    assert any(entry["operation"] == "entity_updated" for entry in agent.hash_chain.get_entries())

    committed = agent.commit_session("sess_001")
    assert committed["status"] == "committed"
    assert committed["entity_ids"] == [original_id]
    assert any(entry["operation"] == "session_commit" for entry in agent.hash_chain.get_entries())

    session_path = tmp_path / "data" / "sessions.json"
    assert json.loads(session_path.read_text(encoding="utf-8"))["sess_001"]["entity_ids"] == [original_id]
    reloaded = SessionStore(path=str(session_path)).get_session("sess_001")
    assert reloaded == committed
    assert reloaded["entity_ids"] == [original_id]
    assert "embedding" not in session_path.read_text(encoding="utf-8")
