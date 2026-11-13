# MNEMOSYNE

MNEMOSYNE is an auditable memory layer for coding agents. It keeps durable memory at entity and session scope, links it in a knowledge graph, retrieves it with vector search, and records lifecycle and deletion evidence.

## What is included

- Session memory shared across agents.
- Knowledge-graph relationships and derived-entity tracking.
- Vector retrieval with bounded context construction.
- Filesystem-backed entity memory for durable inspection.
- Accountability records with actor, reason, timestamp, lifecycle state, and hash-chain evidence.
- Honcho-style dreaming consolidation with a Laya accept/escalate gate and LLM fallback.

## Quick start

Run from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install faiss-cpu
```

Configure an LLM provider before using the normal agent or MCP workflow. The provider configuration is required for the supported runtime path; `none` is only a deterministic unit-test override.

## Required LLM configuration

### Local Ollama

Start Ollama and pull a tool-capable model:

```powershell
ollama serve
ollama pull qwen3:1.7b
$env:MNEMOSYNE_LLM_PROVIDER = "ollama"
$env:MNEMOSYNE_LLM_MODEL = "qwen3:1.7b"
$env:MNEMOSYNE_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
```

### Groq

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "groq"
$env:MNEMOSYNE_LLM_MODEL = "llama-3.1-8b-instant"
$env:GROQ_API_KEY = "your-groq-api-key"
```

The default Groq endpoint is `https://api.groq.com/openai/v1`. Set `MNEMOSYNE_LLM_BASE_URL` only when using a different OpenAI-compatible endpoint. Never commit API keys or a credential-bearing `.env` file.

### Laya dreaming gate

The runtime gate loads the trained checkpoint from `outputs/laya-mnemosyne-gate` by default:

```powershell
$env:MNEMOSYNE_LAYA_GATE_MODEL = "outputs/laya-mnemosyne-gate"
$env:MNEMOSYNE_DREAMING_THRESHOLD = "0.75"
```

If the checkpoint is unavailable, the candidate is escalated directly to the configured LLM. This is a fallback for the gate model; it does not remove the requirement to configure the runtime LLM.

## Where Laya appears

Laya is used only in the post-session dreaming path. It is not called by ordinary `remember`, `recall`, or `forget`.

```text
remember(...)
  -> session entity, graph node, vector, filesystem record, audit evidence

commit_session(...)
  -> entity extraction and summaries
  -> filesystem persistence and session commit
  -> graph orphan healing
  -> dream_session(...)
       -> HonchoDreaming builds a compact candidate
       -> DreamingGate checks evidence support
       -> Laya predicts accept or escalate
       -> accepted candidate becomes a derived dream_summary entity
       -> rejected or uncertain candidate is sent to the configured LLM
       -> unresolved candidates are not persisted

recall(...)
  -> vector and graph retrieval -> bounded active context

forget(...)
  -> remove active source/vector/filesystem content
  -> invalidate descendants and block inference
  -> write deletion accountability and residual-risk evidence
```

Laya therefore reduces LLM calls during consolidation. It decides whether a compact, evidence-supported candidate is safe to accept locally. It does not generate the final chat response and it does not replace the knowledge graph or vector store.

## Basic MCP flow

The MCP server exposes the memory operations used by an agent:

- `start_session` creates or resumes an agent session.
- `remember` stores a durable memory in the active session.
- `recall` retrieves bounded context from graph and vector memory.
- `commit_session` closes the session and runs extraction, healing, and dreaming.
- `dream_session` requests an explicit consolidation pass.
- `preview_delete` shows deletion impact before mutation.
- `delete_memory` performs an accountable deletion after confirmation.

## WSL Ollama MCP inter-session and inter-agent test

This is the smallest real-agent acceptance test. It uses Ollama in WSL, the MCP server over stdio, and the shared persistent MNEMOSYNE stores.

### 1. Prepare WSL

```bash
cd /mnt/d/sahyadri
sudo apt update
sudo apt install -y python3-venv python3-pip build-essential
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install faiss-cpu
python -c "import faiss, mcp; print('dependencies ready')"
```

In a separate WSL terminal, start Ollama and install the model:

```bash
ollama serve
curl http://127.0.0.1:11434/api/tags
ollama pull qwen3:1.7b
```

In the WSL terminal that launches the runner, configure the same provider:

```bash
export MNEMOSYNE_LLM_PROVIDER=ollama
export MNEMOSYNE_LLM_MODEL=qwen3:1.7b
export MNEMOSYNE_LLM_BASE_URL=http://127.0.0.1:11434/v1
```

### 2. Agent A stores a fact

```bash
python scripts/ollama_mcp_cli.py --model qwen3:1.7b --conversation memory-demo-a --agent ollama-agent-a
```

At the prompt, enter:

```text
Remember exactly: DELETE_TEST_2026 — my temporary test color is orange.
Use MNEMOSYNE recall to retrieve DELETE_TEST_2026 and show its exact memory ID.
/exit
```

Record the UUID printed by recall.

### 3. Agent B resumes the same conversation

```bash
python scripts/ollama_mcp_cli.py --model qwen3:1.7b --conversation memory-demo-a --agent ollama-agent-b --resume
```

Ask:

```text
What do I love drinking?
```

The answer should be `orange`. This proves handoff across a new session and agent.

### 4. Agent C uses an independent conversation

```bash
python scripts/ollama_mcp_cli.py --model qwen3:1.7b --conversation memory-demo-independent --agent ollama-agent-c
```

Ask the agent to use MNEMOSYNE recall for `DELETE_TEST_2026`. It should also find `orange`, because durable memory is shared across conversations. Explicitly asking for the tool is useful with small local models.

### 5. Delete and verify from another agent

Start a separate conversation:

```bash
python scripts/ollama_mcp_cli.py --model qwen3:1.7b --conversation deletion-demo --agent ollama-deletion-agent
```

Ask it to:

```text
Use MNEMOSYNE recall to find DELETE_TEST_2026 and show the exact memory ID.
Call preview_delete with that exact ID and show the impact.
After reviewing the impact, call delete_memory with that exact ID and confirmation=true.
```

Then start a fresh verification agent:

```bash
python scripts/ollama_mcp_cli.py --model qwen3:1.7b --conversation deletion-verification --agent ollama-verification-agent
```

Ask:

```text
Use MNEMOSYNE recall to search for DEMO_AGENT_2026. Do not rely on chat history.
```

The deleted memory must not be returned as active context. The deletion response should include the actor, reason, timestamp, lifecycle result, and residual-risk checks. This test writes persistent state under `data/`, including `data/ollama_sessions/`; use synthetic markers only.

The runner is implemented in `scripts/ollama_mcp_cli.py`. It starts `mcp_server.server` over stdio, saves conversation state, starts a new MNEMOSYNE session for each process, and links a resumed session through `parent_session_id`.

## Essential checks

Run the unit suite after code changes:

```powershell
python -m pytest -q
```

Run the adversarial unlearning smoke benchmark:

```powershell
python scripts/bemula_benchmark.py --quick
```

For deterministic unit-only runs, temporarily set `MNEMOSYNE_LLM_PROVIDER=none`; do not use that setting for the normal agent/MCP acceptance test.

## Project map

- `agents/agent_a.py` — public memory, session, dreaming, and deletion orchestration.
- `core/dreaming.py` — Honcho-style candidate consolidation and Laya gate.
- `core/knowledge_graph.py` — entity relationships and lifecycle state.
- `core/vector_store.py` or the active vector-store implementation — semantic retrieval.
- `core/filesystem_memory.py` — durable entity records and redaction.
- `core/graph_healer.py` — orphan detection and repair.
- `mcp_server/server.py` — agent-facing MCP tools.
- `scripts/ollama_mcp_cli.py` — local Ollama inter-session/inter-agent runner.

More detail is kept in:

- [architecture.md](architecture.md)
- [A3 architecture diagram](docs/mnemosyne-architecture-a3.svg)
- [Manual acceptance testing](docs/MANUAL_ACCEPTANCE_TESTING.md)
- [DPO/fine-tuning notes](docs/FINETUNE_DPO.md)
