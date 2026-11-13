import pytest

from core.harness_protocol import HarnessMessage


def test_harness_message_round_trip():
    message = HarnessMessage.create("QUERY", "agent-a", {"query": "Python preference"})
    restored = HarnessMessage.from_json(message.to_json())
    assert restored.command == "QUERY"
    assert restored.sender == "agent-a"
    assert restored.payload["query"] == "Python preference"
    assert restored.correlation_id == message.correlation_id


def test_harness_message_rejects_unknown_command():
    with pytest.raises(ValueError):
        HarnessMessage.create("RUN_ARBITRARY_CODE", "agent-a")
