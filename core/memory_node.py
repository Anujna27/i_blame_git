from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import uuid

@dataclass
class MemoryNode:
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    source: dict = field(default_factory=dict)
    trust_status: str = "user_asserted"
    derivation_edges: list[dict] = field(default_factory=list)
    version: int = 1
    supersedes: Optional[str] = None
    contradicts: list[str] = field(default_factory=list)
    deletion_state: str = "active"
    is_blocked: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    entity_type: str = "memory"
    lifecycle: list[dict] = field(default_factory=list)
    deleted_reason: Optional[str] = None
    deleted_by: Optional[str] = None
    deleted_at: Optional[datetime] = None
    def __post_init__(self):
        if not self.lifecycle:
            self.lifecycle.append({"state": "created", "actor": "system",
                                   "reason": "entity_created", "timestamp": self.created_at.isoformat()})
    def to_jsonld(self):
        data=asdict(self)
        for key in ("created_at", "last_accessed", "deleted_at"):
            if data.get(key) is not None:
                data[key] = data[key].isoformat()
        return data
    @classmethod
    def from_jsonld(cls,data):
        values=dict(data)
        for key in ("created_at","last_accessed","deleted_at"):
            if isinstance(values.get(key),str): values[key]=datetime.fromisoformat(values[key])
        return cls(**values)

    def transition(self, state: str, actor: str = "system", reason: str = ""):
        """Record every entity state transition, including deletion provenance."""
        now = datetime.now(timezone.utc)
        self.deletion_state = state
        self.lifecycle.append({"state": state, "actor": actor, "reason": reason,
                               "timestamp": now.isoformat()})
        if state != "active":
            self.deleted_by, self.deleted_reason, self.deleted_at = actor, reason, now
    def add_derivation(self,child_id,edge_type):
        edge={"child_id":child_id,"type":edge_type}
        if edge not in self.derivation_edges: self.derivation_edges.append(edge)
