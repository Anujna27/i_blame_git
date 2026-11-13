# BEMULA-R: Rigorous Adversarial Unlearning Evaluation

- Target instances: **102** (+300 untouched background nodes), seed 1337, top-k 25
- **RPR: 100.00%** (102/102), Wilson 95% CI [96.37%, 100.0%]
- Silent leaks (leak with no engine disclosure): **0**; disclosed leaks: 0
- Vacuous instances (no probe found target pre-deletion): 0
- Background collateral failures: 0/40; delete latency p50/p95: 1169.61/1418.94 ms

## Per-type

- F1 (Factual): 17/17 (100.00%)
- F2 (Compositional): 17/17 (100.00%)
- F3 (Semantic Category): 17/17 (100.00%)
- F4 (Inferential): 17/17 (100.00%)
- F5 (Temporal): 17/17 (100.00%)
- F6 (Replacement): 17/17 (100.00%)
- Retrieval calls: 1454 (mean 5.3 ms); engine warnings during retrieval: 0

## Failing checks (instances affected)

- none

## Edge cases

- redelete_exceptions: 0
- redelete_state_stable: True
- audit_bytes_growth_on_redelete: 8087
- unknown_id_graceful: True
- audit_chain_valid: True
- audit_tamper_detected: True

## Stress scenarios


## Harness self-test (mutation kill rate; must be high or the harness is vacuous)


## Definition

An instance passes only if, both immediately and after cold reload: the target is inactive and scrubbed; every dependent (derived, replacement, cross-session and paraphrased duplicates) is forgotten; no active node, vector hit or on-disk byte contains the secret; adversarial probes at k=1/5/top-k retrieve nothing forgotten; the block and audit records exist; and every preserve-labelled node (context, prefix-collision sibling, neighbour) is intact, unaltered and still retrievable.
