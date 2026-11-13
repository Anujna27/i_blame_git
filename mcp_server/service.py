"""Dependency-free application service used by the MCP adapter.

The service deliberately delegates all mutations to the existing AgentA and
store implementations.  This keeps MCP as a transport boundary rather than
creating a second memory implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.agent_a import AgentA
from core.active_context import ContextBuilder


class MnemosyneService:
    """Safe, session-aware facade for local agents such as Ollama."""

    def __init__(self, agent: AgentA | None = None) -> None:
        self.agent = agent or AgentA()

    @staticmethod
    def _node_summary(node: Any) -> dict[str, Any]:
        return {
            "node_id": node.node_id,
            "content": node.content,
            "summary": node.summary_l1 or node.content,
            "deletion_state": node.deletion_state,
            "trust_status": node.trust_status,
            "session_id": node.session_id,
            "access_count": node.access_count,
            "last_accessed": node.last_accessed.isoformat() if node.last_accessed else None,
        }

    def start_session(
        self,
        session_id: str,
        agent_id: str,
        parent_session_id: str | None = None,
    ) -> dict[str, Any]:
        if not session_id.strip() or not agent_id.strip():
            raise ValueError("session_id and agent_id are required")
        record = self.agent.sessions.get_session(session_id)
        nodes = self.agent.recall_session(session_id)
        parent_summary = self.session_summary(parent_session_id) if parent_session_id else None
        return {
            "session_id": session_id,
            "agent_id": agent_id,
            "parent_session_id": parent_session_id,
            "existing": record is not None,
            "session": record,
            "active_memories": [self._node_summary(node) for node in nodes],
            "parent_summary": parent_summary,
        }

    def remember(
        self,
        content: str,
        session_id: str,
        agent_id: str,
        source_type: str = "conversation_turn",
        trust_status: str = "user_asserted",
        turn_index: int = 0,
    ) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("content is required")
        node = self.agent.remember(
            content,
            source_type=source_type,
            session_id=session_id,
            turn_index=turn_index,
            trust_status=trust_status,
        )
        node.properties["last_agent_id"] = agent_id
        self.agent.graph.persist()
        return self._node_summary(node)

    def recall(
        self,
        query: str,
        session_id: str,
        token_budget: int = 2000,
        top_k: int = 5,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("query is required")
        if token_budget <= 0 or top_k <= 0:
            raise ValueError("token_budget and top_k must be positive")
        builder = ContextBuilder(
            self.agent.vector_store,
            self.agent.graph,
            self.agent.session_store,
            token_budget=token_budget,
        )
        # ContextBuilder currently uses a fixed retrieval size.  Restricting
        # the result here keeps the MCP contract explicit without changing the
        # existing AgentA behavior used by the demo and claim tests.
        context = builder.build_context(query, session_id=session_id)
        entities = context.entities[:top_k]
        abstained, abstention_reason = self.agent.abstention.should_abstain(query, entities)
        return {
            "answer": "" if abstained else "\n".join(entity.summary_l1 or entity.content for entity in entities),
            "memory_ids": [] if abstained else [entity.node_id for entity in entities],
            "memories": [] if abstained else [self._node_summary(entity) for entity in entities],
            "tokens_used": sum(len((entity.summary_l1 or entity.content).split()) for entity in entities),
            "ranking_explanations": context.ranking_explanations[:top_k],
            "abstained": abstained,
            "abstention_reason": abstention_reason,
            "session_id": session_id,
        }

    def commit_session(self, session_id: str, agent_id: str, reason: str = "session_end") -> dict[str, Any]:
        result = self.agent.commit_session(session_id, actor=agent_id, reason=reason)
        return {"session_id": session_id, "agent_id": agent_id, "commit": result}

    def dream_session(self, session_id: str, agent_id: str, token_budget: int = 256) -> dict[str, Any]:
        """Run the local dreaming/Laya gate for a session on demand."""
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        return self.agent.dream_session(
            session_id,
            actor=agent_id,
            reason="mcp_dreaming_request",
            token_budget=token_budget,
        )

    def preview_delete(self, node_id: str) -> dict[str, Any]:
        node = self.agent.graph.get_node(node_id)
        if node is None:
            raise KeyError(f"Unknown memory: {node_id}")
        descendants = self.agent.graph.get_descendants(node_id)
        candidates = self.agent.vector_store.query(node.content, top_k=10)
        relevant = []
        for candidate in candidates:
            if candidate.node_id == node_id or candidate.deletion_state != "active":
                continue
            similarity = self.agent.erasure._similar(node.content, candidate.content)
            if similarity > 0.75:
                relevant.append({"node_id": candidate.node_id, "similarity": round(similarity, 3)})
        last_accessed = node.last_accessed
        days_since_access = max(
            0, (datetime.now(timezone.utc) - last_accessed).days
        ) if last_accessed else None
        return {
            "node_id": node_id,
            "relevance_score": max((item["similarity"] for item in relevant), default=0.0),
            "relevant_neighbors": relevant,
            "access_count": node.access_count,
            "days_since_last_access": days_since_access,
            "derived_memories": len(descendants),
            "hard_delete_supported": True,
            "soft_delete_supported": False,
            "warning": "Hard deletion is irreversible; only audit metadata and digest evidence remain.",
        }

    def delete_memory(
        self,
        node_id: str,
        agent_id: str,
        reason: str = "user_requested_erasure",
        confirmation: bool = False,
    ) -> dict[str, Any]:
        if not confirmation:
            raise PermissionError("Deletion requires confirmation=true")
        report = self.agent.forget(node_id, reason=reason, deleted_by=agent_id)
        return {
            "node_id": report.node_id,
            "verdict": report.verdict,
            "deleted_at": report.timestamp,
            "deleted_by": report.deleted_by,
            "reason": report.reason,
            "levels": [level.__dict__ for level in report.levels],
            "residual_risks": [risk.__dict__ for risk in report.residual_risks],
        }

    def session_summary(self, session_id: str) -> dict[str, Any]:
        record = self.agent.sessions.get_session(session_id)
        nodes = self.agent.recall_session(session_id)
        return {
            "session_id": session_id,
            "session": record,
            "active_memories": [self._node_summary(node) for node in nodes],
            "blocked_memory_ids": sorted(self.agent.blocked_ids),
            "last_audit_entry": self.agent.hash_chain.get_entries()[-1] if self.agent.hash_chain.get_entries() else None,
        }

    def export_context_capsule(self, agent_id: str) -> dict[str, Any]:
        capsule = self.agent.export_memory()
        return {
            "capsule_id": capsule["capsule_id"],
            "source_agent": agent_id,
            "path": str(Path("data/capsules") / f"cap_{capsule['capsule_id']}.json"),
            "memory_count": len(capsule.get("memory_nodes", [])),
            "deleted_count": len(capsule.get("deletion_audit", {}).get("deleted_nodes", [])),
        }

