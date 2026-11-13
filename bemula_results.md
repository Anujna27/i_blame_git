# BEMULA Evaluation — 102-Instance Rigorous Real-Stack Benchmark

- Instances evaluated: **102**
- Rigorous Real-Stack RPR: **100.00%** (102 / 102)
- Baseline: **1.5%**
- Semantic/Adversarial leaks: **0 / 102 (0.00%)**

## Per-type RPR

- F1 (Factual): 17/17 (100.00%)
- F2 (Compositional): 17/17 (100.00%)
- F3 (Semantic Category): 17/17 (100.00%)
- F4 (Inferential): 17/17 (100.00%)
- F5 (Temporal): 17/17 (100.00%)
- F6 (Replacement): 17/17 (100.00%)

## Failure breakdown

- Forget only: 0
- Preservation only: 0
- Both: 0

## Definition

A request passes when the target is structurally non-active, entirely unretrievable via adversarial vector semantic probes, inference blocking is recorded, and unrelated preserved data remains active.
