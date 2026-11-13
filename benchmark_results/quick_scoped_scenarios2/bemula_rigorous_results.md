# BEMULA-R: Rigorous Adversarial Unlearning Evaluation

- Target instances: **6** (+12 untouched background nodes), seed 1337, top-k 25
- **RPR: 100.00%** (6/6), Wilson 95% CI [60.97%, 100.0%]
- Silent leaks (leak with no engine disclosure): **0**; disclosed leaks: 0
- Vacuous instances (no probe found target pre-deletion): 0
- Background collateral failures: 0/12; delete latency p50/p95: 100.64/112.8 ms

## Per-type

- F1 (Factual): 1/1 (100.00%)
- F2 (Compositional): 1/1 (100.00%)
- F3 (Semantic Category): 1/1 (100.00%)
- F4 (Inferential): 1/1 (100.00%)
- F5 (Temporal): 1/1 (100.00%)
- F6 (Replacement): 1/1 (100.00%)
- Retrieval calls: 76 (mean 0.5 ms); engine warnings during retrieval: 0

## Failing checks (instances affected)

- none

## Edge cases

- redelete_exceptions: 0
- redelete_state_stable: True
- audit_bytes_growth_on_redelete: 4851
- unknown_id_graceful: True
- audit_chain_valid: True
- audit_tamper_detected: True

## Stress scenarios

- **concurrent**: {'instances': 6, 'passed': 6, 'rpr': 100.0, 'silent_leaks': 0, 'disclosed_leaks': 0, 'vacuous_probe_instances': 0, 'worker_exceptions': 0, 'audit_chain_valid': True}
- **fault_injection**: {'instances': 6, 'passed': 6, 'rpr': 100.0, 'silent_leaks': 0, 'disclosed_leaks': 0, 'vacuous_probe_instances': 0, 'fault_applicable': True, 'loud_failures': 6, 'silent_failures': 0}
- **control**: {'instances': 6, 'passed': 6, 'rpr': 100.0, 'silent_leaks': 0, 'disclosed_leaks': 0, 'vacuous_probe_instances': 0}

## Harness self-test (mutation kill rate; must be high or the harness is vacuous)

- vector_noop: `imm.target_vec_gone` caught 100.0% of sabotaged deletions (control false-alarms: 0)
- graph_noop: `imm.target_inactive` caught 100.0% of sabotaged deletions (control false-alarms: 0)
- audit_noop: `global.audit_entry` caught 100.0% of sabotaged deletions (control false-alarms: 0)

## Definition

An instance passes only if, both immediately and after cold reload: the target is inactive and scrubbed; every dependent (derived, replacement, cross-session and paraphrased duplicates) is forgotten; no active node, vector hit or on-disk byte contains the secret; adversarial probes at k=1/5/top-k retrieve nothing forgotten; the block and audit records exist; and every preserve-labelled node (context, prefix-collision sibling, neighbour) is intact, unaltered and still retrievable.
