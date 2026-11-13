# MNEMOSYNE MCP server for Ollama

The MCP server is a thin adapter over the existing `AgentA` service. It uses
stdio, so an MCP-capable Ollama runner can launch it as a local subprocess.

## Install

From the repository root:

```powershell
python -m pip install -r requirements.txt
```

The Ollama server must also be running locally. Use a model that supports tool
calling.

## Run the MCP server directly

```powershell
python -m mcp_server.server
```

The process communicates over stdin/stdout. Do not print ordinary logging to
stdout; MCP uses stdout for protocol messages.

## Exposed capabilities

Tools:

- `start_session`: resume durable context for an agent and session.
- `remember`: persist a memory with session and agent identity.
- `recall`: retrieve deletion-safe session-aware context.
- `commit_session`: persist a handover point and run core dreaming consolidation.
- `dream_session`: explicitly run the local dreaming/Laya gate for a session.
- `preview_delete`: inspect relevance, frequency, descendants, and risks.
- `delete_memory`: permanently delete after explicit confirmation.
- `export_context_capsule`: create a portable memory capsule.

Resource:

```text
mnemosyne://sessions/{session_id}/summary
```

The resource contains the active memories and blocked IDs required to continue
a session after switching agents.

## Ollama integration boundary

Ollama produces tool calls, but a host application must execute the MCP calls
and feed the results back to Ollama. The intended loop is:

```text
discover MCP tools
  -> send schemas to Ollama /api/chat
  -> receive tool call
  -> execute MCP tool
  -> append tool result to the Ollama messages
  -> repeat until final answer
```

The model should always pass both `session_id` and `agent_id`. The session ID
is the continuity key; the agent ID records which local model or harness made
the change.

## Interactive Ollama runner

The repository includes a local runner that launches the MCP server, discovers
its tools, and executes Ollama tool calls:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3 \
  --conversation project-001 \
  --agent ollama-agent-a
```

Stop with `/exit`. Resume the same logical conversation in a fresh session or
agent with:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3 \
  --conversation project-001 \
  --agent ollama-agent-b \
  --resume
```

Conversation state is stored under `data/ollama_sessions/`. A resumed run gets
a new session ID and receives the previous session ID as `parent_session_id`.

## Safety behavior

`delete_memory` is intentionally hard-delete-only in this first adapter because
the existing erasure engine implements hard erasure. It requires
`confirmation=true`. Call `preview_delete` first. Soft deletion should be
added to the core erasure engine before it is exposed as an MCP option.

