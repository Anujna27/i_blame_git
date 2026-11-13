"""_stdio MCP server exposing MNEMOSYNE to an Ollama tool-calling runner.

Run from the repository root with:

    python -m mcp_server.server

The server uses stdio so an MCP host can launch it as a local subprocess.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from .service import MnemosyneService

try:
    # MCP SDK v2.
    from mcp.server.mcpserver import MCPServer
except ImportError:  # pragma: no cover - compatibility for MCP SDK v1 hosts
    from mcp.server.fastmcp import FastMCP as MCPServer


mcp = MCPServer(
    "mnemosyne",
    instructions=(
        "Use MNEMOSYNE for durable memory across sessions and agents. "
        "Always provide session_id and agent_id. Preview deletion before deleting."
    ),
)
service = MnemosyneService()


@mcp.tool()
def start_session(
    session_id: str,
    agent_id: str,
    parent_session_id: str | None = None,
) -> dict[str, Any]:
    """Start or resume a durable MNEMOSYNE session."""
    return service.start_session(session_id, agent_id, parent_session_id)


@mcp.tool()
def remember(
    content: str,
    session_id: str,
    agent_id: str,
    source_type: str = "conversation_turn",
    trust_status: str = "user_asserted",
    turn_index: int = 0,
) -> dict[str, Any]:
    """Store a durable memory linked to a session and agent."""
    return service.remember(content, session_id, agent_id, source_type, trust_status, turn_index)


@mcp.tool()
def recall(query: str, session_id: str, token_budget: int = 2000, top_k: int = 5) -> dict[str, Any]:
    """Retrieve deletion-safe, session-aware context."""
    return service.recall(query, session_id, token_budget, top_k)


@mcp.tool()
def commit_session(session_id: str, agent_id: str, reason: str = "session_end") -> dict[str, Any]:
    """Commit a session so a later agent can continue it."""
    return service.commit_session(session_id, agent_id, reason)


@mcp.tool()
def dream_session(session_id: str, agent_id: str, token_budget: int = 256) -> dict[str, Any]:
    """Consolidate active session memories through the local dreaming gate."""
    return service.dream_session(session_id, agent_id, token_budget)


@mcp.tool()
def preview_delete(node_id: str) -> dict[str, Any]:
    """Inspect relevance, usage, descendants, and risks before deletion."""
    return service.preview_delete(node_id)


@mcp.tool()
def delete_memory(
    node_id: str,
    agent_id: str,
    reason: str = "user_requested_erasure",
    confirmation: bool = False,
) -> dict[str, Any]:
    """Permanently delete a memory after explicit confirmation."""
    return service.delete_memory(node_id, agent_id, reason, confirmation)


@mcp.resource("mnemosyne://sessions/{session_id}/summary")
def session_summary(session_id: str) -> dict[str, Any]:
    """Read the durable summary needed to continue a session."""
    return service.session_summary(session_id)


@mcp.tool()
def export_context_capsule(agent_id: str) -> dict[str, Any]:
    """Export the current durable memory state for another agent."""
    return service.export_context_capsule(agent_id)


def main() -> None:
    runner = getattr(mcp, "run", None)
    if runner is None:
        raise RuntimeError("Installed MCP SDK does not expose a runnable server")
    result = runner(transport="stdio")
    if inspect.isawaitable(result):
        asyncio.run(result)


if __name__ == "__main__":
    main()

