from datetime import datetime, timezone
from typing import Literal, Optional
import uuid
from pydantic import BaseModel, Field, field_validator


class MemoryNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    source: dict
    trust_status: Literal["verified", "user_asserted", "derived", "contradicted", "planted"] = "user_asserted"
    derivation_edges: list[dict] = Field(default_factory=list)
    version: int = 1
    supersedes: Optional[str] = None
    contradicts: list[str] = Field(default_factory=list)
    deletion_state: Literal["active", "source_removed", "invalidated"] = "active"
    is_blocked: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0

    @field_validator("source")
    @classmethod
    def validate_source(cls, value):
        required = {"type", "session_id", "turn_index", "timestamp", "raw_reference"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"source missing keys: {sorted(missing)}")
        return value

    def to_jsonld(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_jsonld(cls, data: dict) -> "MemoryNode":
        return cls.model_validate(data)

    def add_derivation(self, child_id: str, edge_type: str) -> None:
        edge = {"child_id": child_id, "type": edge_type}
        if edge not in self.derivation_edges:
            self.derivation_edges.append(edge)
