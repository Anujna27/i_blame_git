# MNEMOSYNE

MNEMOSYNE is an auditable memory system combining session-scoped entities, a knowledge graph, vector retrieval, lifecycle auditing, and residual-risk reporting.

## ChatGPT memory bridge

The bridge imports a Gemini chat export and exposes MNEMOSYNE memory through a FastAPI endpoint for a Custom GPT Action.

Install the bridge dependencies:

```powershell
python -m pip install -r requirements.txt
```

Place the Gemini export at `data/gemini_import/gemini_chat.json`, then run ingestion from the repository root:

```powershell
python ingest_gemini.py
```

Start the API server:

```powershell
uvicorn api_server:app --port 8000
```

In another terminal, expose it with Ngrok:

```powershell
ngrok http 8000
```

In the Custom GPT editor, add an Action using the root `openapi.json` file. Replace its `servers[0].url` value with the HTTPS Ngrok URL shown by `ngrok http 8000` (without a trailing slash), then import or paste the updated schema into the Action configuration. The Action sends `{"query":"..."}` to `POST /search_memory` and receives `{"answer":"..."}`.

## Claim audit framework

The claim audit is a standalone testing tool. It does not modify the application implementation. It runs tests under `tests/claims/` and `tests/adversarial/`, prints a terminal summary, and writes judge-facing reports under `data/claims/`.

Run commands from the repository root:

```powershell
cd D:\sahyadri
```

### Basic syntax

```powershell
python scripts/run_claim_audit.py [options]
```

Common options:

| Option | Meaning | Default |
|---|---|---:|
| `--list` | List every claim and adversarial test without running it | off |
| `--claims-only` | Run only the 14 claim tests | off |
| `--adversarial-only` | Run only the 10 adversarial tests | off |
| `--claim N` | Run one claim, such as `--claim 1` | all claims |
| `--adversarial NAME` | Run one adversarial module, such as `--adversarial test_tamper_audit` | all adversarial tests |
| `--node-count N` | Number of erasure scenarios/descendants | `1` |
| `--sessions N` | Number of restart-persistence sessions | `30` |
| `--token-budget N` | Maximum tokens allowed in active context | `200` |
| `--seed N` | Reproducibility seed passed to tests | `42` |
| `--heal-threshold X` | Similarity threshold passed to healing tests | `0.75` |
| `--output json` | Write only JSON report | `both` |
| `--output markdown` | Write only Markdown report | `both` |
| `--quiet` | Suppress per-test terminal lines | off |

Custom values can be combined:

```powershell
python scripts/run_claim_audit.py --node-count 5 --sessions 30 --token-budget 500 --seed 42 --heal-threshold 0.80
```

## Recommended execution sequence

List the available tests:

```powershell
python scripts/run_claim_audit.py --list
```

Run one claim:

```powershell
python scripts/run_claim_audit.py --claim 1
```

Run one adversarial test:

```powershell
python scripts/run_claim_audit.py --adversarial test_tamper_audit
```

Run all claims:

```powershell
python scripts/run_claim_audit.py --claims-only
```

Run all adversarial tests:

```powershell
python scripts/run_claim_audit.py --adversarial-only
```

Run the complete audit:

```powershell
python scripts/run_claim_audit.py
```

The process exits with code `0` for `GREEN` or `YELLOW`, and code `1` for `RED`.

## Claim tests

Each claim module defines `run(context)` and returns `PASS`, `FAIL`, or `SKIP` with details and structured evidence.

| Command | What it validates | Custom values |
|---|---|---|
| `--claim 1` | Five-level erasure report, verdict, and audit-chain integrity | `--node-count` |
| `--claim 2` | Deleted parent and invalidated child survive restart | none |
| `--claim 3` | Hash-chain tampering is detected | none |
| `--claim 4` | Capsule preserves deletion state across handover | none |
| `--claim 5` | Capsule preserves residual-risk information | none |
| `--claim 6` | Session commit triggers graph orphan healing or quarantine | `--heal-threshold` |
| `--claim 7` | Verified memories outrank planted memories in vector retrieval | none |
| `--claim 8` | Active context stays within the requested token budget | `--token-budget` |
| `--claim 9` | Contradictory user assertions are detected | none |
| `--claim 10` | Insufficient evidence causes abstention | none |
| `--claim 11` | Lifecycle audit records actor, reason, and timestamp | none |
| `--claim 12` | Legacy capsules remain importable | none |
| `--claim 13` | Multiple sessions survive restart | `--sessions` |
| `--claim 14` | Mid-task cross-agent handover preserves task memory | none |

Examples:

```powershell
# Five erasure scenarios with up to five descendants
python scripts/run_claim_audit.py --claim 1 --node-count 5

# Test a 500-token active context
python scripts/run_claim_audit.py --claim 8 --token-budget 500

# Test 50 sessions with a reproducible seed
python scripts/run_claim_audit.py --claim 13 --sessions 50 --seed 42

# Test healing at a stricter similarity threshold
python scripts/run_claim_audit.py --claim 6 --heal-threshold 0.85
```

## Adversarial tests

Run an individual adversarial test with:

```powershell
python scripts/run_claim_audit.py --adversarial test_delete_missing_node
```

Available adversarial modules:

| Module | What it attacks |
|---|---|
| `test_delete_missing_node` | Deletion of a nonexistent entity |
| `test_double_delete` | Repeated deletion of the same entity |
| `test_tamper_audit` | Modification of a persisted audit entry |
| `test_broken_capsule` | Import of a corrupted capsule |
| `test_planted_memory` | False/planted memory retrieval safety |
| `test_no_evidence_abstention` | Query with no evidence |
| `test_planted_only_abstention` | Query where all evidence is planted |
| `test_forced_contradiction` | Conflicting verified memories |
| `test_token_budget_overflow` | Attempt to exceed a strict token budget |
| `test_restart_mid_task` | Restart during an unfinished task |

Examples:

```powershell
python scripts/run_claim_audit.py --adversarial test_token_budget_overflow --token-budget 10
python scripts/run_claim_audit.py --adversarial test_tamper_audit --seed 7
```

## Reports

The latest run writes:

- `data/claims/claim_audit_report.json` — machine-readable report containing context, commit, Python version, individual results, evidence, errors, and summary counts.
- `data/claims/claim_audit_report.md` — judge-facing Markdown report with claim/adversarial tables and failure details.

Each test result has this shape:

```json
{
  "name": "Hash chain detects tampering",
  "status": "PASS",
  "details": "in-memory tamper checked",
  "evidence": {"original_ok": true, "post_tamper_ok": false},
  "error": null
}
```

Overall status is calculated as:

- `GREEN`: every selected test passes.
- `YELLOW`: at least one test is skipped and none fails.
- `RED`: at least one test fails.

`SKIP` is used only when the requested claim cannot be evaluated against an available interface. It is not counted as a pass.

## Running the normal unit suite

The claim audit is separate from the project’s pytest suite. Run both when validating a change:

```powershell
python -m pytest -q
python scripts/run_claim_audit.py
```

The pytest suite validates implementation behavior. The claim audit translates the system’s public claims into standalone, judge-facing evidence.

## Optional LLM configuration

LLM-backed extraction and summarization are opt-in. If a `.env` file exists, MNEMOSYNE loads it automatically; without valid provider configuration, deterministic local fallbacks are used.

### Enable OpenAI-backed extraction and summaries

PowerShell:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "openai"
$env:MNEMOSYNE_LLM_MODEL = "gpt-4o-mini"
$env:OPENAI_API_KEY = "your-api-key"
python -m pytest -q
python scripts/run_claim_audit.py
```

For deterministic unit tests, disable network-backed features explicitly:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "none"
python -m pytest -q
```

Optional OpenAI-compatible endpoints are supported:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "openai_compatible"
$env:MNEMOSYNE_LLM_BASE_URL = "https://your-endpoint.example/v1"
$env:MNEMOSYNE_LLM_MODEL = "your-model"
$env:OPENAI_API_KEY = "your-api-key"
```

Groq is supported through its OpenAI-compatible endpoint:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "groq"
$env:MNEMOSYNE_LLM_MODEL = "llama-3.1-8b-instant"
$env:GROQ_API_KEY = "your-groq-api-key"
```

For a local Ollama demo, start Ollama and pull a model:

```powershell
ollama pull llama3.2:3b
$env:MNEMOSYNE_LLM_PROVIDER = "ollama"
$env:MNEMOSYNE_LLM_MODEL = "llama3.2:3b"
# Optional remote Ollama endpoint:
# $env:MNEMOSYNE_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
```

Ollama is local and does not require an API key. The adapter uses its
OpenAI-compatible `/v1` endpoint. Set `MNEMOSYNE_LLM_PROVIDER=none` to run
without LLM calls.

For the WSL MCP runner, set these variables in the same WSL terminal before
starting the runner so core summaries, dreaming escalation, and graph-healing
suggestions use the same local Ollama model:

```bash
export MNEMOSYNE_LLM_PROVIDER=ollama
export MNEMOSYNE_LLM_MODEL=qwen3:1.7b
export MNEMOSYNE_LLM_BASE_URL=http://127.0.0.1:11434/v1
```

The default Groq endpoint is `https://api.groq.com/openai/v1`. Override it with `MNEMOSYNE_LLM_BASE_URL` if needed. When using Groq, configure `GROQ_API_KEY`; when using OpenAI or another compatible endpoint, configure `OPENAI_API_KEY`.

The optional Python SDK must be installed in the active environment:

```powershell
python -m pip install openai
```

When enabled, the provider is used for:

- session entity extraction during `commit_session()`;
- generated L0/L1/L2 summaries;
- future injectable graph-healing suggestions.

The adapter requests JSON-only responses and validates the returned shape. If the SDK is unavailable, credentials are missing, or a provider call fails, the local deterministic fallback remains available to the application.

Groq rate and request limits apply to all LLM-backed features. In particular, orphan-link healing can build a larger prompt than summary generation because it includes graph context. If Groq reports an input-tokens-per-minute error such as `Requested 7624` against a `7000` ITPM limit, the healing suggestion call will fail gracefully and the local healing path will continue. Use a smaller graph/session scope, a model or service tier with a higher ITPM limit, or run healing with the LLM provider disabled when deterministic behavior is preferred. Summary generation and session commit are not discarded when an optional healing suggestion fails.

To disable the provider for the current PowerShell session:

```powershell
Remove-Item Env:MNEMOSYNE_LLM_PROVIDER -ErrorAction SilentlyContinue
Remove-Item Env:MNEMOSYNE_LLM_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:MNEMOSYNE_LLM_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:GROQ_API_KEY -ErrorAction SilentlyContinue
```

Never commit API keys or `.env` files containing credentials. Use environment variables or a secret manager.

## WSL Ollama MCP inter-session and inter-agent test

This is the live acceptance test for the local Ollama/MNEMOSYNE workflow. It
uses Ollama inside WSL, the MCP server over stdio, and the shared persistent
MNEMOSYNE stores. Observal is not required.

### 1. Prepare WSL

Run these commands in Ubuntu/WSL from the repository root:

```bash
cd /mnt/d/devhost/mnemosyne
sudo apt update
sudo apt install -y python3-venv python3-pip build-essential zstd
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install faiss-cpu
python -c "import faiss, mcp; print('dependencies ready')"
```

### 2. Start Ollama in WSL

Use a separate WSL terminal and leave the server running:

```bash
ollama serve
```

In another terminal, verify it and install a small tool-capable model:

```bash
curl http://127.0.0.1:11434/api/tags
ollama pull qwen3:1.7b
ollama list
```

### 2a. Enable the core Ollama provider

Set these variables in the same WSL terminal that launches the MCP runner:

```bash
export MNEMOSYNE_LLM_PROVIDER=ollama
export MNEMOSYNE_LLM_MODEL=qwen3:1.7b
export MNEMOSYNE_LLM_BASE_URL=http://127.0.0.1:11434/v1
```

The MCP path still uses the core MNEMOSYNE pipeline. `remember` performs the
normal graph, contradiction, vector, session, and audit work. `recall` applies
bounded retrieval and abstention. `commit_session` runs entity extraction,
graph healing, and the dreaming consolidation pass. Laya evaluates dreaming
candidates locally when its gate checkpoint is available; only ambiguous or
low-confidence candidates escalate to Ollama. The MCP `dream_session` tool can
also request an explicit pass.

Repeated preference evidence is consolidated before it is sent to the model.
For example, 20 active mentions of vanilla and 15 of chocolate produce a
counted preference summary rather than sending all 35 duplicate sentences.

### 3. Create durable memory with Agent A

From the project root with `.venv` active:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3:1.7b \
  --conversation memory-demo-a \
  --agent ollama-agent-a
```

At the `You:` prompt, enter:

```text
Remember this test fact exactly: DELETE_TEST_2026 — my temporary test color is orange.
```

The response should show `[tool] remember`. Verify it before exiting:

```text
Use MNEMOSYNE recall to retrieve DELETE_TEST_2026 and show the exact memory ID.
```

Record the returned UUID. Exit cleanly:

```text
/exit
```

### 4. Resume in a new session and agent

This creates a new session linked to the previous session:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3:1.7b \
  --conversation memory-demo-a \
  --agent ollama-agent-b \
  --resume
```

Ask:

```text
Use MNEMOSYNE recall to retrieve DELETE_TEST_2026. What temporary color was stored?
```

The response should show `[tool] recall` and return `orange`. This verifies
inter-session and inter-agent continuity.

### 5. Recall from an independent conversation

Do not use `--resume` and use a different conversation ID:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3:1.7b \
  --conversation memory-demo-independent \
  --agent ollama-agent-c
```

Ask:

```text
Use MNEMOSYNE recall to find DELETE_TEST_2026. What temporary color was stored?
```

It should still return `orange`, because durable memories are shared across
agents and conversations. A normal question without asking the model to use
recall may not trigger the tool in a small local model.

### 6. Preview and delete from another agent

Start a separate deletion test conversation:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3:1.7b \
  --conversation deletion-demo \
  --agent ollama-deletion-agent
```

First retrieve the exact UUID:

```text
Use MNEMOSYNE recall to find DELETE_TEST_2026 and show the exact memory ID.
```

Then preview it using the UUID returned by recall, not the text
`DELETE_TEST_2026`:

```text
Call preview_delete using the exact memory ID for DELETE_TEST_2026 and show the deletion impact.
```

Review relevance, access count, descendants, and residual-risk information.
Only then request deletion:

```text
Call delete_memory using that exact memory ID with confirmation=true. Delete only DELETE_TEST_2026.
```

The response should show `[tool] delete_memory` and an erasure verdict. The
current MCP adapter exposes hard deletion only. It preserves audit metadata
and removes the active content/vector representation.

Exit with:

```text
/exit
```

### 7. Verify deletion from a fresh agent

Start another independent conversation:

```bash
python scripts/ollama_mcp_cli.py \
  --model qwen3:1.7b \
  --conversation deletion-verification \
  --agent ollama-verification-agent
```

Ask:

```text
Use MNEMOSYNE recall to search for DELETE_TEST_2026. Do not rely on chat history.
```

The deleted memory must not be returned as active context. An abstention or
`no active memory found` result is expected.

These tests create persistent files under `data/`, including the audit log,
vector metadata, graph data, session state, and `data/ollama_sessions/`. Use a
unique test marker and do not use real personal data. The deletion step is
irreversible.

## Healing worker and retrieval benchmark

Run one healing pass:

```powershell
python scripts/run_healing_worker.py --once
```

Run the persistent worker:

```powershell
python scripts/run_healing_worker.py --interval 900
```

Benchmark hybrid retrieval:

```powershell
python scripts/benchmark_retrieval.py --sessions 30 --token-budget 500
```

Benchmark end-to-end deletion completion over an isolated synthetic corpus:

```powershell
python scripts/benchmark_deletion_rate.py --count 1000
```

The benchmark creates a target, a derived child, an unrelated entity, and filesystem-memory records for every request in a temporary directory. It simulates a restart and counts a request as successful only when the target and derived records are non-active in the graph, absent from vectors, redacted from filesystem memory, inference-blocked, auditable, and unrelated data remains available. It compares this strict operational rate with the 1.5% benchmark baseline. Use `--count 1000` for a larger run. The benchmark does not modify the repository's normal `data/` stores.

Simulate a realistic customer account-erasure request:

```powershell
python scripts/simulate_real_life_deletion.py
```

This creates a customer profile, preferences, purchase history, a derived support summary, and an unrelated second customer. It then deletes the first customer's profile and prints the deletion report plus a post-erasure inventory. The expected result is that the first customer's records are non-active, redacted, and absent from the vector store, while the unrelated customer's record remains active. A `partially_deleted` verdict is expected when derived history prevents a literal return to a never-written state; this is distinct from failure to remove active records.

LLM usage telemetry is available from an `AgentA` instance:

```python
agent.llm_telemetry()
```

It reports provider, model, calls, failures, and token counts without exposing credentials.

## Preference fine-tuning (Path B)

The synthetic compaction corpus can be used for DPO fine-tuning of a causal
multilingual model. The recommended small baseline is
`Qwen/Qwen2.5-1.5B-Instruct`; `convaiinnovations/laya-multilingual` is a
classification model and is not a direct DPO generation target. See
[docs/FINETUNE_DPO.md](docs/FINETUNE_DPO.md) for environment setup, a
dataset-only validation command, a 10-step GPU smoke run, and the full
1,920-example training command.

## RLHF and Honcho dreaming

The training/runtime layers are:

```text
Qwen DPO adapter -> policy/generator
Laya gate        -> local reward and accept/escalate decision
GRPO             -> online RLHF-style policy update using Laya rewards
Honcho dreaming  -> session consolidation and LLM escalation
```

Train the Laya gate:

```powershell
$env:HF_HUB_DISABLE_XET = "1"
.\.venv-dpo\Scripts\python.exe scripts/finetune_laya_gate.py --epochs 1 --output-dir outputs/laya-mnemosyne-gate
```

Run an online RLHF smoke update:

```powershell
.\.venv-dpo\Scripts\python.exe scripts/rlhf_grpo_compaction.py --max-train-samples 8 --max-steps 2 --output-dir outputs/mnemosyne-rlhf-grpo
```

`AgentA.dream_session(session_id)` consolidates active session entities, and
`commit_session()` invokes it automatically after the session is committed.
Laya accepts supported candidates locally; unsupported or low-confidence
candidates are escalated to the configured LLM. Accepted or LLM-resolved
summaries are stored as derived entities with `DERIVED_FROM` edges and
hash-chain records. The MCP server also exposes `dream_session` for an
explicit consolidation pass.
If Laya is unavailable, the system escalates and does not silently persist the
candidate.
