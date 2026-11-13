# MNEMOSYNE Manual Acceptance Testing

This guide tests MNEMOSYNE as a potential user would use it: creating memory, committing sessions, switching sessions, restarting or changing agents, measuring bounded context, testing graph/vector retrieval, and deleting an entity while inspecting exactly what was removed.

Run all commands from the repository root:

```powershell
Set-Location D:\sahyadri
```

## 1. Choose the test mode

Run deterministic tests first with the LLM disabled:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "none"
```

Then repeat the LLM-specific checks with Groq enabled:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "groq"
```

The `.env` file supplies the configured model and API key. Never print or commit the key.

To confirm only the provider configuration, without exposing credentials:

```powershell
python -c "from core.llm_config import ConfiguredLLM; print(ConfiguredLLM().telemetry())"
```

Expected disabled output has `enabled: False`; Groq output should identify the provider and model without displaying the API key.

## 2. Run the automated baseline first

Use the disabled-provider mode for a repeatable baseline:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "none"
python -m pytest -q
```

Expected result: all tests pass. This confirms that the manual test is starting from a healthy implementation.

Run the claim audit:

```powershell
python scripts/run_claim_audit.py
```

Expected result:

- 14 claim tests pass.
- 10 adversarial tests pass.
- Overall status is `GREEN`.

## 3. Create a manual user-flow script

Create `scripts/manual_user_flow.py` with the following content:

```python
import json

from agents.agent_a import AgentA
from core.active_context import ContextBuilder


def show_context(agent, session_id, query, budget=80):
    builder = ContextBuilder(
        agent.vector_store,
        agent.graph,
        agent.session_store,
        token_budget=budget,
    )
    context = builder.build_context(query, session_id=session_id)

    print(f"\\nSESSION: {session_id}")
    print(f"QUERY: {query}")
    print(f"TOKENS USED: {context.token_count}/{budget}")
    print(f"VECTOR IDS: {context.vector_entity_ids}")
    print(f"GRAPH IDS: {context.graph_entity_ids}")
    print("CONTEXT:")
    print(context.text or "<empty>")
    return context


agent_a = AgentA()

# Session A: user preferences and project context.
alice = agent_a.remember(
    "Alice prefers Python and uses FastAPI for backend services.",
    session_id="manual_session_a",
    turn_index=1,
)

api_key = agent_a.remember(
    "Alice's temporary API key is sk-test-user-123.",
    session_id="manual_session_a",
    turn_index=2,
)

agent_a.remember(
    "Alice is building a memory system with graph and vector retrieval.",
    session_id="manual_session_a",
    turn_index=3,
)

# Session B: deliberately unrelated deployment context.
agent_a.remember(
    "The project deployment target is a Windows server.",
    session_id="manual_session_b",
    turn_index=1,
)

agent_a.remember(
    "The deployment uses PowerShell automation.",
    session_id="manual_session_b",
    turn_index=2,
)

print("\\nCOMMIT SESSION A")
print(json.dumps(
    agent_a.commit_session(
        "manual_session_a",
        actor="manual-user",
        reason="finished planning",
    ),
    indent=2,
    default=str,
))

print("\\nCOMMIT SESSION B")
print(json.dumps(
    agent_a.commit_session(
        "manual_session_b",
        actor="manual-user",
        reason="finished deployment discussion",
    ),
    indent=2,
    default=str,
))

print("\\nLLM TELEMETRY AFTER COMMIT")
print(json.dumps(agent_a.llm_telemetry(), indent=2, default=str))

# A new instance simulates a process restart or another harness.
print("\\nSTARTING A NEW AGENT INSTANCE")
agent_b = AgentA()

context_a = show_context(
    agent_b,
    "manual_session_a",
    "What programming language and backend framework does Alice prefer?",
    budget=40,
)

context_b = show_context(
    agent_b,
    "manual_session_b",
    "How will the project be deployed?",
    budget=40,
)

# Session isolation assertions.
assert any("Python" in entity.content for entity in context_a.entities)
assert not any("PowerShell" in entity.content for entity in context_a.entities)
assert any("PowerShell" in entity.content for entity in context_b.entities)
assert not any("Python" in entity.content for entity in context_b.entities)
print("\\nSESSION ISOLATION: PASS")

# Delete the credential and print the complete erasure result.
print("\\nDELETING API KEY")
deletion = agent_b.forget(
    api_key.node_id,
    reason="user requested removal of temporary credential",
    deleted_by="alice",
)
print(json.dumps(deletion.to_dict(), indent=2, default=str))

assert agent_b.graph.get_node(api_key.node_id).deletion_state != "active"
assert agent_b.vector_store.get_by_id(api_key.node_id) is None

post_delete = show_context(
    agent_b,
    "manual_session_a",
    "What is Alice's temporary API key?",
    budget=40,
)
assert api_key.node_id not in [entity.node_id for entity in post_delete.entities]
print("\\nDELETION RETRIEVAL CHECK: PASS")

print("\\nFINAL LLM TELEMETRY")
print(json.dumps(agent_b.llm_telemetry(), indent=2, default=str))
print("\\nOVERALL MANUAL ACCEPTANCE TEST: PASS")
```

Run it with the LLM disabled:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "none"
python scripts/manual_user_flow.py
```

Repeat with Groq:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "groq"
python scripts/manual_user_flow.py
```

The script uses `ContextBuilder` with an explicit `session_id` because the convenience method `AgentA.recall()` currently defaults to `sess_001`.

## 4. Test session persistence and session swapping

The manual script creates two sessions:

- `manual_session_a`: Python, FastAPI, graph/vector memory, and a temporary credential.
- `manual_session_b`: Windows and PowerShell deployment details.

Inspect committed session metadata:

```powershell
Get-Content data\sessions.json | ConvertFrom-Json | ConvertTo-Json -Depth 20
```

Verify that both session IDs exist and that each contains only its own entity IDs.

Test explicit session swapping interactively:

```powershell
@'
from agents.agent_a import AgentA
from core.active_context import ContextBuilder

agent = AgentA()
builder = ContextBuilder(agent.vector_store, agent.graph, agent.session_store, token_budget=40)

for session_id, query in [
    ("manual_session_a", "What does Alice prefer?"),
    ("manual_session_b", "What is the deployment environment?"),
    ("manual_session_a", "What memory system is being built?"),
]:
    context = builder.build_context(query, session_id=session_id)
    print(session_id, context.token_count, [x.node_id for x in context.entities])
    print(context.text)
'@ | python
```

Expected result: changing `session_id` changes the eligible memory set without requiring a new process.

## 5. Test agent/harness switching

A new `AgentA()` instance simulates a new harness process using the same persisted stores:

```powershell
python -c "from agents.agent_a import AgentA; a=AgentA(); print(len(a.all_nodes)); print(list(a.sessions._sessions.keys()))"
```

The new instance should see entities and sessions created by the previous instance.

For an explicit Agent A to Agent B capsule handoff:

```powershell
python scripts/verify_capsule_roundtrip.py
```

Inspect generated capsule files:

```powershell
Get-ChildItem data\capsules | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

The handoff must preserve active entities, deletion blocks, lifecycle state, graph data, and vector snapshot metadata.

## 6. Test token consumption and bounded context

Run the retrieval benchmark:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "none"
python scripts/benchmark_retrieval.py --sessions 30 --token-budget 100
python scripts/benchmark_retrieval.py --sessions 30 --token-budget 500
```

Compare the output for the two budgets. The selected context must never exceed the configured budget.

For a direct check, use:

```powershell
python -c "from agents.agent_a import AgentA; a=AgentA(); c=a.build_active_context('Python backend preference', token_budget=20); print({'tokens': c.token_count, 'entities': [x.node_id for x in c.entities], 'vector': c.vector_entity_ids, 'graph': c.graph_entity_ids})"
```

Inspect:

- `token_count`: actual selected context size.
- `vector_entity_ids`: entities found by semantic retrieval.
- `graph_entity_ids`: entities added by graph expansion.
- `text`: the memory actually supplied to a harness.

For a meaningful comparison, run the same query with budgets of 20, 80, and 300. A larger budget may include more related entities, but it must not exceed the requested limit.

## 7. Verify hybrid knowledge-graph and vector retrieval

Use a query whose wording differs from the stored fact:

```powershell
@'
from agents.agent_a import AgentA

agent = AgentA()
context = agent.build_active_context("backend web framework preference", token_budget=100)
print("vector matches:", context.vector_entity_ids)
print("graph expansions:", context.graph_entity_ids)
print(context.text)
'@ | python
```

Inspect the graph directly:

```powershell
$graph = Get-Content data\knowledge_graph.json | ConvertFrom-Json
$graph | ConvertTo-Json -Depth 30
```

The vector IDs should identify semantic matches. Graph IDs should identify related entities reached through graph relationships. If the query finds only a vector match and no graph expansion, that is valid when no relationship exists.

## 8. Test entity lifecycle and updates

Create and update an entity:

```powershell
@'
from agents.agent_a import AgentA
import json

agent = AgentA()
node = agent.remember("I prefer dark mode.", session_id="lifecycle_session", turn_index=1)
print("created:", node.node_id, node.lifecycle_state, node.version)

updated = agent.update_entity(
    node.node_id,
    "I prefer light mode during the day and dark mode at night.",
    actor="manual-user",
    reason="user corrected preference",
)
print("updated:", updated.node_id, updated.lifecycle_state, updated.version)
print(json.dumps(updated.lifecycle_history, indent=2, default=str))
'@ | python
```

Expected result:

- The same entity ID remains present.
- The version increases.
- The lifecycle history contains the update actor, reason, and timestamp.
- `data/audit_chain.json` contains an `entity_updated` event.

## 9. Test deletion and measure its actual impact

The deletion report is the primary result:

```python
report = agent.forget(
    node_id,
    reason="user requested removal",
    deleted_by="manual-user",
)
print(report.to_dict())
```

Check each deletion level:

### Level 1: source record

Verify the graph node remains only as an auditable deleted record and is no longer active:

```powershell
$graph = Get-Content data\knowledge_graph.json | ConvertFrom-Json
$graph | ConvertTo-Json -Depth 30
```

The entity should have a non-active `deletion_state`, and its content should be redacted.

### Level 2: derived artifacts

The report field `levels[1].evidence` shows:

- `total_descendants`
- `invalidated_children`
- `failed_children`

If the deleted entity had graph descendants, those derived entities should be invalidated and their active vector entries removed.

### Level 3: inference block

Inspect:

```powershell
Get-Content data\blocked_inference.json | ConvertFrom-Json
```

The deleted entity ID must be present.

### Level 4: semantic residual risk

Inspect `report.residual_risks` and `levels[3].evidence`.

This identifies active neighboring entities whose content may still allow partial reconstruction. A `partially_deleted` verdict is expected when such risks exist.

### Level 5: restoration check

Inspect `levels[4].evidence.non_reversible_artifacts`.

If derived artifacts existed, the report should explain that returning to a never-written state cannot be guaranteed.

### Audit accountability

Search the audit chain:

```powershell
$events = Get-Content data\audit_chain.json | ConvertFrom-Json
$events | Where-Object { $_.event_type -match "delete|deletion" } | Format-List
```

Confirm that the deletion event contains:

- entity ID;
- actor/deleter;
- reason;
- timestamp;
- content digest/signature;
- deletion verdict.

The raw deleted content must not remain in the active graph/vector stores. The audit record should retain accountability metadata and digest evidence, not the deleted secret itself.

## 10. Verify deletion cannot be retrieved after restart

After deleting an entity, start a completely new process:

```powershell
python -c "from agents.agent_a import AgentA; a=AgentA(); print(a.blocked_ids); print(a.vector_store.query('temporary API key', top_k=10))"
```

Expected result:

- The deleted ID appears in `blocked_ids`.
- The deleted entity is absent from active vector results.
- The deleted content is absent from normal graph context.

## 11. Test orphan detection and healing

Run one healing pass:

```powershell
python scripts/run_healing_worker.py --once
```

Inspect the printed report for:

- orphan count;
- healed count;
- quarantined count;
- healing actions;
- suggested links when the LLM provider is enabled.

Run the worker periodically in a separate terminal:

```powershell
python scripts/run_healing_worker.py --interval 900
```

Stop it with `Ctrl+C`.

Inspect graph state before and after the worker:

```powershell
Get-Content data\knowledge_graph.json | ConvertFrom-Json | ConvertTo-Json -Depth 30
```

Healing must not silently delete unknown nodes. Nodes that cannot be safely repaired should be quarantined and reported.

## 12. Test LLM extraction and generated summaries

Run the manual flow with Groq enabled:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER = "groq"
python scripts/manual_user_flow.py
```

Inspect the filesystem memory output:

```powershell
Get-ChildItem data\viking_memory -Recurse
Get-Content data\viking_memory\*.json | ConvertFrom-Json | ConvertTo-Json -Depth 20
```

For each committed entity, inspect:

- `summary_l0`: compact retrieval summary;
- `summary_l1`: richer contextual summary;
- `content_l2`: detailed content;
- extracted entity/property metadata.

Compare the output against a disabled-provider run. With Groq enabled, telemetry should show provider calls and generated summaries/extraction. If the provider fails, the system should report the failure and use the deterministic fallback rather than losing the memory.

## 13. Quick deletion test (single command)

This is the shortest end-to-end deletion test. It creates one active entity, retrieves it, deletes it, prints the audit report, and verifies that the entity is absent from vector retrieval afterward. It does not commit the session, which avoids confusing the deletion check with orphan healing.

Run from `D:\sahyadri`:

```powershell
$env:MNEMOSYNE_LLM_PROVIDER="none"; @'
from agents.agent_a import AgentA
import json

agent = AgentA()
node = agent.remember(
    "UNIQUE_DELETE_TEST_84721 temporary credential",
    session_id="delete_test_84721",
)

print("CREATED", node.node_id, node.deletion_state)
print("BEFORE DELETE", [n.node_id for n in agent.vector_store.query("UNIQUE_DELETE_TEST_84721", top_k=10)])

report = agent.forget(
    node.node_id,
    reason="manual deletion test",
    deleted_by="manual-user",
)
print("DELETION REPORT")
print(json.dumps(report.to_dict(), indent=2, default=str))

after = agent.vector_store.query("UNIQUE_DELETE_TEST_84721", top_k=10)
print("AFTER DELETE", [n.node_id for n in after])
print("PASS" if node.node_id not in [n.node_id for n in after] else "FAIL")
'@ | python
```

Expected result:

- Initial state is `active`.
- The entity ID appears before deletion.
- The verdict is `fully_deleted` when there are no derived artifacts or semantic risks.
- The entity ID does not appear after deletion.
- The report contains the actor, reason, timestamp, deletion levels, residual risks, and signature.

## 14. Quick non-LLM versus Groq comparison

This command runs the same memory input twice in separate Python processes: once with the provider disabled and once with Groq enabled. Separate processes are important because provider configuration is loaded when `AgentA` is created.

```powershell
@'
from agents.agent_a import AgentA
import json
import uuid

text = (
    "Himanshu is building MNEMOSYNE, a memory system using a knowledge graph "
    "and vector retrieval. He prefers Python and wants deletion accountability."
)

session_id = "comparison_" + uuid.uuid4().hex[:8]
agent = AgentA()
node = agent.remember(text, session_id=session_id, turn_index=1)
commit = agent.commit_session(session_id, actor="comparison-test", reason="LLM comparison")

print(json.dumps({
    "provider": agent.llm_telemetry()["provider"],
    "enabled": agent.llm_telemetry()["enabled"],
    "node_id": node.node_id,
    "summary_l0": node.summary_l0,
    "summary_l1": node.summary_l1,
    "content_l2": node.content_l2,
    "commit": commit,
    "telemetry": agent.llm_telemetry(),
}, indent=2, default=str))
'@ | ForEach-Object {
    Write-Host "`n========== NON-LLM RUN ==========" -ForegroundColor Cyan
    $env:MNEMOSYNE_LLM_PROVIDER = "none"
    $_ | python

    Write-Host "`n========== GROQ LLM RUN ==========" -ForegroundColor Green
    $env:MNEMOSYNE_LLM_PROVIDER = "groq"
    $_ | python
}
```

Compare `summary_l0`, `summary_l1`, `telemetry.calls`, `telemetry.failures`, `input_tokens`, and `output_tokens`. The disabled run should have zero LLM calls. The Groq run should show generated summaries and positive token counts. If Groq reaches its input-token-per-minute limit during optional orphan-link healing, a warning may appear while the session commit and summary result still complete through fallback behavior.

## 15. Inspect all persistent test evidence

Important files under `data`:

| Path | What to inspect |
|---|---|
| `data/knowledge_graph.json` | Entities, relationships, lifecycle, deletion state |
| `data/sessions.json` | Sessions, commits, entity membership |
| `data/chroma_db/` | Persisted vector index |
| `data/audit_chain.json` | Accountability and hash-chain events |
| `data/blocked_inference.json` | Deleted IDs blocked from inference |
| `data/viking_memory/` | Filesystem-style entity records and summary tiers |
| `data/capsules/` | Exported handoff snapshots |
| `data/claims/` | Claim-audit reports |
| `data/healing_schedule.json` | Healing worker configuration |

Useful commands:

```powershell
Get-ChildItem data -Recurse | Sort-Object FullName
Get-Content data\audit_chain.json | ConvertFrom-Json | ConvertTo-Json -Depth 30
Get-Content data\knowledge_graph.json | ConvertFrom-Json | ConvertTo-Json -Depth 30
```

## 16. Cleanup after manual testing

Manual tests write persistent records. If the data is disposable, remove only the generated test entities through the application or move the test data directory aside after verifying results. Do not delete the repository or broad workspace paths.

Before a clean automated run, use a dedicated test data configuration if available. Otherwise, preserve the evidence first and then restore only the specific generated files/directories created by the manual run.

## Acceptance checklist

- [ ] Baseline pytest suite passes.
- [ ] Claim audit reports `GREEN`.
- [ ] Two committed sessions can be swapped without context leakage.
- [ ] A new agent instance sees committed memory.
- [ ] Capsule handoff preserves lifecycle and deletion state.
- [ ] Context stays within the requested token budget.
- [ ] Vector IDs and graph IDs are visible separately.
- [ ] Entity updates preserve ID and create lifecycle/audit history.
- [ ] Deletion reports actor, reason, timestamp, verdict, affected descendants, and residual risks.
- [ ] Deleted content is absent from active vector retrieval after restart.
- [ ] Orphans are healed or quarantined and never silently discarded.
- [ ] Groq mode produces telemetry and LLM summaries/extraction when configured.
