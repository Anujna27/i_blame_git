"""Small, explicit command envelope for harness-to-harness integration.

This is transport-neutral: callers may send the JSON over a queue, HTTP, or a
shared process boundary. The protocol validates identity and correlation before
dispatching to an application adapter.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import uuid

COMMANDS = {
    "REMEMBER", "COMMIT_SESSION", "QUERY", "DELETE_ENTITY",
    "EXPORT_CAPSULE", "IMPORT_CAPSULE", "HEALTH",
}


@dataclass
class HarnessMessage:
    command: str
    sender: str
    payload: dict
    correlation_id: str
    created_at: str
    protocol_version: str = "1"

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def create(cls, command: str, sender: str, payload=None, correlation_id=None):
        command = command.upper()
        if command not in COMMANDS:
            raise ValueError(f"unsupported harness command: {command}")
        if not sender:
            raise ValueError("sender is required")
        return cls(command, sender, payload or {}, correlation_id or str(uuid.uuid4()), datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_json(cls, value: str):
        data = json.loads(value)
        required = {"command", "sender", "payload", "correlation_id", "created_at", "protocol_version"}
        missing = required.difference(data)
        if missing:
            raise ValueError(f"missing protocol fields: {sorted(missing)}")
        message = cls(**data)
        if message.command not in COMMANDS:
            raise ValueError(f"unsupported harness command: {message.command}")
        if not isinstance(message.payload, dict) or not message.sender:
            raise ValueError("invalid harness message identity or payload")
        return message
