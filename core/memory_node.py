# STUB — waiting for M1/M2/M3
from dataclasses import dataclass, field, asdict
from typing import Literal
from datetime import datetime, timezone
import uuid

@dataclass
class MemoryNode:
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    source: dict = field(default_factory=dict)
    trust_status: Literal["verified","user_asserted","derived","contradicted","planted"] = "user_asserted"
    derivation_edges: list[dict] = field(default_factory=list)
    version: int = 1
    supersedes: str | None = None
    contradicts: list[str] = field(default_factory=list)
    deletion_state: Literal["active","source_removed","invalidated"] = "active"
    is_blocked: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed: str | None = None
    access_count: int = 0

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, data): return cls(**data)
