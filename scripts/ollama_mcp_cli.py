"""Interactive Ollama CLI backed by the MNEMOSYNE MCP server.

Run from the repository root:

    python scripts/ollama_mcp_cli.py --model qwen3 --conversation project-001 --agent ollama-a

Resume in a fresh agent/session:

    python scripts/ollama_mcp_cli.py --model qwen3 --conversation project-001 --agent ollama-b --resume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from mcp import Client, StdioServerParameters
except ImportError as exc:  # pragma: no cover - exercised by the CLI environment
    raise SystemExit("Install the MCP SDK first: python -m pip install 'mcp>=2.0,<3'") from exc


DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
STATE_DIR = Path("data") / "ollama_sessions"


def _json_request(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url.rstrip("/") + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach Ollama at {url}. Start Ollama and verify OLLAMA_HOST."
        ) from exc


def _tool_schema(tool: Any) -> dict[str, Any]:
    data = tool.model_dump(by_alias=True, exclude_none=True) if hasattr(tool, "model_dump") else {
        "name": tool.name,
        "description": getattr(tool, "description", ""),
        "inputSchema": getattr(tool, "inputSchema", {"type": "object"}),
    }
    return {
        "type": "function",
        "function": {
            "name": data["name"],
            "description": data.get("description", ""),
            "parameters": data.get("inputSchema", data.get("input_schema", {"type": "object"})),
        },
    }


def _content_text(result: Any) -> str:
    blocks = result.content if hasattr(result, "content") else result.get("content", [])
    parts = []
    for block in blocks:
        if hasattr(block, "text"):
            parts.append(block.text)
        elif isinstance(block, dict) and "text" in block:
            parts.append(str(block["text"]))
        else:
            parts.append(json.dumps(block, default=str))
    return "\n".join(parts)


def _load_state(conversation_id: str) -> dict[str, Any] | None:
    path = STATE_DIR / f"{conversation_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{state['conversation_id']}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def _message_from_response(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return message if isinstance(message, dict) else {"role": "assistant", "content": str(message)}


def _normalize_tool_arguments(
    name: str | None,
    arguments: Any,
    user_text: str,
    session_id: str,
) -> dict[str, Any]:
    """Repair common small-model omissions before MCP validation."""
    normalized = dict(arguments) if isinstance(arguments, dict) else {}
    if name == "recall":
        query = normalized.get("query")
        if not isinstance(query, str) or not query.strip():
            query = user_text
        active_session = normalized.get("session_id")
        if not isinstance(active_session, str) or not active_session.strip():
            active_session = session_id
        normalized["query"] = query
        normalized["session_id"] = active_session
        if not isinstance(normalized.get("token_budget"), int):
            normalized["token_budget"] = 2000
        if not isinstance(normalized.get("top_k"), int):
            normalized["top_k"] = 5
    return normalized


async def run(args: argparse.Namespace) -> None:
    previous = _load_state(args.conversation)
    if args.resume and previous is None:
        raise SystemExit(f"No saved conversation named {args.conversation!r}")

    session_id = str(uuid.uuid4())
    parent_session_id = previous.get("session_id") if previous else None
    messages = list(previous.get("messages", [])) if previous and args.resume else []
    if not messages:
        messages = [{"role": "system", "content": (
            "You are a local Ollama agent using MNEMOSYNE for durable memory. "
            "The runner has already initialized the MNEMOSYNE session. Use recall "
            "for context, remember durable facts, and commit_session before exit. "
            "Commit automatically runs the core dreaming consolidation; use "
            "dream_session when an explicit consolidation pass is needed."
        )}]

    project_root = Path(__file__).resolve().parents[1]
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env={**os.environ, "PYTHONPATH": str(project_root)},
    )

    async with Client(server_params) as mcp_client:
        start_result = await mcp_client.call_tool(
            "start_session",
            {
                "session_id": session_id,
                "agent_id": args.agent,
                "parent_session_id": parent_session_id,
            },
        )
        messages.append({"role": "system", "content": f"MNEMOSYNE context:\n{_content_text(start_result)}"})
        listed = await mcp_client.list_tools()
        tools = [_tool_schema(tool) for tool in listed.tools]

        state = {
            "conversation_id": args.conversation,
            "session_id": session_id,
            "agent_id": args.agent,
            "parent_session_id": parent_session_id,
            "model": args.model,
            "messages": messages,
        }
        _save_state(state)

        print(f"Conversation: {args.conversation}\nSession: {session_id}")
        if parent_session_id:
            print(f"Resumed from: {parent_session_id}")
        print("Type /exit to stop. State is saved after every turn.")

        while True:
            try:
                user_text = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue
            if user_text.lower() in {"/exit", "/quit"}:
                break

            messages.append({"role": "user", "content": user_text})
            # Do not rely on a small local model to decide whether a question
            # needs memory or to construct a valid recall schema.  Prefetching
            # makes independent agents see shared durable memory reliably.
            automatic_recall = await mcp_client.call_tool(
                "recall",
                {"query": user_text, "session_id": session_id, "token_budget": 2000, "top_k": 5},
            )
            messages.append({
                "role": "system",
                "content": (
                    "Automatic MNEMOSYNE recall for this user turn. Use it as "
                    "durable evidence and do not claim that memory is unavailable:\n"
                    f"{_content_text(automatic_recall)}"
                ),
            })
            print("[auto] recall")
            while True:
                response = _json_request(
                    args.ollama_url,
                    {"model": args.model, "messages": messages, "tools": tools, "stream": False},
                )
                message = response.get("message", {})
                messages.append(_message_from_response(message))
                tool_calls = message.get("tool_calls", [])
                if not tool_calls:
                    print(f"\n{message.get('content', '')}")
                    break

                for call in tool_calls:
                    function = call.get("function", {})
                    name = function.get("name")
                    arguments = function.get("arguments", {})
                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)
                    arguments = _normalize_tool_arguments(name, arguments, user_text, session_id)
                    result = await mcp_client.call_tool(name, arguments)
                    messages.append({"role": "tool", "tool_name": name, "content": _content_text(result)})
                    print(f"[tool] {name}")

            state["messages"] = messages
            _save_state(state)

        # A clean CLI exit always creates a durable handover checkpoint, even
        # if the model did not issue commit_session itself.
        await mcp_client.call_tool(
            "commit_session",
            {"session_id": session_id, "agent_id": args.agent, "reason": "cli_exit"},
        )
        state["messages"] = messages
        _save_state(state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Ollama with MNEMOSYNE MCP tools")
    parser.add_argument("--model", required=True, help="Ollama model name, for example qwen3")
    parser.add_argument("--conversation", required=True, help="Stable logical conversation ID")
    parser.add_argument("--agent", required=True, help="Agent identity for audit and handover")
    parser.add_argument("--resume", action="store_true", help="Start a fresh session from saved conversation state")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()

