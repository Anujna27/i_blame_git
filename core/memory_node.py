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
    def to_jsonld(self):
        data=asdict(self); data["created_at"]=self.created_at.isoformat(); data["last_accessed"]=self.last_accessed.isoformat(); return data
    @classmethod
    def from_jsonld(cls,data):
        values=dict(data)
        for key in ("created_at","last_accessed"):
            if isinstance(values.get(key),str): values[key]=datetime.fromisoformat(values[key])
        return cls(**values)
    def add_derivation(self,child_id,edge_type):
        edge={"child_id":child_id,"type":edge_type}
        if edge not in self.derivation_edges: self.derivation_edges.append(edge)
