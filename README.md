# MNEMOSYNE

MNEMOSYNE is an auditable memory system combining session-scoped entities, a knowledge graph, vector retrieval, lifecycle auditing, and residual-risk reporting.

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

LLM usage telemetry is available from an `AgentA` instance:

```python
agent.llm_telemetry()
```

It reports provider, model, calls, failures, and token counts without exposing credentials.
