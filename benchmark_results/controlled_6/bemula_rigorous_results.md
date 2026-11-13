# BEMULA-R: Rigorous Adversarial Unlearning Evaluation

- Target instances: **6** (+10 untouched background nodes), seed 1337, top-k 25
- **RPR: 0.00%** (0/6), Wilson 95% CI [0.0%, 39.03%]
- Silent leaks (leak with no engine disclosure): **0**; disclosed leaks: 6
- Vacuous instances (no probe found target pre-deletion): 0
- Background collateral failures: 0/40; delete latency p50/p95: 139.01/160.84 ms

## Per-type

- F1 (Factual): 0/1 (0.00%)
- F2 (Compositional): 0/1 (0.00%)
- F3 (Semantic Category): 0/1 (0.00%)
- F4 (Inferential): 0/1 (0.00%)
- F5 (Temporal): 0/1 (0.00%)
- F6 (Replacement): 0/1 (0.00%)
- Retrieval calls: 96 (mean 360.2 ms); engine warnings during retrieval: 2292

## Failing checks (instances affected)

- `imm.deps_forgotten`: 6
- `imm.no_content_leak`: 6
- `imm.probes_clean`: 6
- `imm.report_clean`: 6
- `reload.target_scrubbed`: 6
- `reload.deps_forgotten`: 6
- `reload.no_content_leak`: 6
- `reload.probes_clean`: 6
- `global.disk_clean`: 6

## Edge cases

- redelete_exceptions: 0
- redelete_state_stable: True
- audit_bytes_growth_on_redelete: 4620
- unknown_id_graceful: True
- audit_chain_valid: True
- audit_tamper_detected: True

## Stress scenarios


## Harness self-test (mutation kill rate; must be high or the harness is vacuous)


## Plaintext residue on disk after erasure

- knowledge_graph.json
- vectors\bemula_main_meta.json
- viking_memory\user\memories\0498aaeb-bf36-4095-b203-a78b850416f0.json
- viking_memory\user\memories\0f830bc8-d1ef-46b7-ad7e-f9879f931a59.json
- viking_memory\user\memories\10c312b3-c676-4c65-a2d6-671f746830f0.json
- viking_memory\user\memories\3f31c2ac-ed4b-4599-9aea-e6b36053db4f.json
- viking_memory\user\memories\5a38cc39-4f23-430d-ab02-c8fe68035732.json
- viking_memory\user\memories\820c2174-6cd2-451c-9d73-b8c89e351867.json
- viking_memory\user\memories\d66b5d16-e725-4d16-8af6-759d06f60d3c.json

## Definition

An instance passes only if, both immediately and after cold reload: the target is inactive and scrubbed; every dependent (derived, replacement, cross-session and paraphrased duplicates) is forgotten; no active node, vector hit or on-disk byte contains the secret; adversarial probes at k=1/5/top-k retrieve nothing forgotten; the block and audit records exist; and every preserve-labelled node (context, prefix-collision sibling, neighbour) is intact, unaltered and still retrievable.
