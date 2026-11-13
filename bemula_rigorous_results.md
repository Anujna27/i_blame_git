# BEMULA-R: Rigorous Adversarial Unlearning Evaluation

- Target instances: **24** (+40 untouched background nodes), seed 1337, top-k 25
- **RPR: 0.00%** (0/24), Wilson 95% CI [0.0%, 13.8%]
- Silent leaks (leak with no engine disclosure): **0**; disclosed leaks: 24
- Vacuous instances (no probe found target pre-deletion): 0
- Background collateral failures: 0/40; delete latency p50/p95: 305.09/377.34 ms

## Per-type

- F1 (Factual): 0/4 (0.00%)
- F2 (Compositional): 0/4 (0.00%)
- F3 (Semantic Category): 0/4 (0.00%)
- F4 (Inferential): 0/4 (0.00%)
- F5 (Temporal): 0/4 (0.00%)
- F6 (Replacement): 0/4 (0.00%)
- Retrieval calls: 375 (mean 1095.9 ms); engine warnings during retrieval: 40891

## Failing checks (instances affected)

- `imm.deps_forgotten`: 24
- `imm.no_content_leak`: 24
- `imm.probes_clean`: 24
- `imm.report_clean`: 24
- `reload.target_scrubbed`: 24
- `reload.deps_forgotten`: 24
- `reload.no_content_leak`: 24
- `reload.probes_clean`: 24
- `global.disk_clean`: 24
- `imm.preserve_ok`: 4
- `imm.preserve_retrievable`: 4
- `reload.preserve_ok`: 4
- `reload.preserve_retrievable`: 4

## Edge cases

- redelete_exceptions: 0
- redelete_state_stable: False
- audit_bytes_growth_on_redelete: 7700
- unknown_id_graceful: True
- audit_chain_valid: True
- audit_tamper_detected: True

## Stress scenarios

- **concurrent**: {'instances': 12, 'passed': 0, 'rpr': 0.0, 'silent_leaks': 0, 'disclosed_leaks': 12, 'vacuous_probe_instances': 0, 'worker_exceptions': 1, 'audit_chain_valid': True}
- **fault_injection**: {'instances': 12, 'passed': 0, 'rpr': 0.0, 'silent_leaks': 12, 'disclosed_leaks': 0, 'vacuous_probe_instances': 0, 'fault_applicable': True, 'loud_failures': 12, 'silent_failures': 0}
- **control**: {'instances': 12, 'passed': 0, 'rpr': 0.0, 'silent_leaks': 0, 'disclosed_leaks': 12, 'vacuous_probe_instances': 0}

## Harness self-test (mutation kill rate; must be high or the harness is vacuous)

- vector_noop: `imm.target_vec_gone` caught 100.0% of sabotaged deletions (control false-alarms: 0)
- graph_noop: `imm.target_inactive` caught 0.0% of sabotaged deletions (control false-alarms: 0)  <-- HARNESS TOO WEAK
- audit_noop: `global.audit_entry` caught 100.0% of sabotaged deletions (control false-alarms: 0)

## Plaintext residue on disk after erasure

- knowledge_graph.json
- vectors\bemula_main_meta.json

## Definition

An instance passes only if, both immediately and after cold reload: the target is inactive and scrubbed; every dependent (derived, replacement, cross-session and paraphrased duplicates) is forgotten; no active node, vector hit or on-disk byte contains the secret; adversarial probes at k=1/5/top-k retrieve nothing forgotten; the block and audit records exist; and every preserve-labelled node (context, prefix-collision sibling, neighbour) is intact, unaltered and still retrievable.
