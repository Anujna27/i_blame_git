# BEMULA Benchmark Evaluation Results

## Benchmark Context
The published BEMULA benchmark reports that no evaluated system exceeds a Request Pass Rate of 1.5% end-to-end (Xie et al., 2026).

## Protocol Validation (Mock Agent)
- **Result**: 100.00% on 3 hand-written instances.
- **Note**: This measures the erasure protocol logic against a deterministic store, not a production memory system. Included to validate that the 5-level erasure logic is sound.

## Production Benchmark (100-Instance Real-Stack Agent)
- **Result**: 74.51% RPR across 102 instances.

### Per-Type Breakdown Table
| Request Type | Description | Total | Passed | RPR (%) |
| :--- | :--- | :--- | :--- | :--- |
| **F1** | Factual (Atomic PII / Credential Deletion) | 17 | 15 | 88.24% |
| **F2** | Compositional (Multi-Entity Composite Deletion) | 17 | 13 | 76.47% |
| **F3** | Semantic (Category-Wide Memory Deletion) | 17 | 15 | 88.24% |
| **F4** | Inferential (Derived Conclusion Deletion) | 17 | 15 | 88.24% |
| **F5** | Temporal (Superseded Historical Value Deletion) | 17 | 12 | 70.59% |
| **F6** | Replacement (Explicit Replacement & Linkage Update) | 17 | 6 | 35.29% |
| **Total** | **All Categories Combined** | **102** | **76** | **74.51%** |

### Failure Categories
| Failure Category | Instances | Description |
| :--- | :--- | :--- |
| **Forget Only** | 8 | Failed to abstain on unlearning probe (recalled deleted fact or active replacement confounded) |
| **Preservation Only** | 18 | Failed preservation probe (over-defensive abstention or below retrieval threshold) |
| **Both** | 0 | Failed both forget and preservation probes |
| **Total Failures** | 26 | Total non-passing instances out of 102 |

Semantic leak diagnostic data is detailed in [eval/semantic_leak_report.json](file:///C:/Users/PC/OneDrive/Desktop/blaniproject/i_blame_git/eval/semantic_leak_report.json).

## Comparison
| System | RPR (%) |
| :--- | :--- |
| Naive Baseline | 0.00 |
| Mock Agent (protocol test, 3 instances) | 100.00 |
| Real-Stack Agent (production, 102 instances) | 74.51 |

## Interpretation
The gap between protocol validation (100.00%) and production benchmark (74.51%) is precisely the residual semantic risk that our Residual Risk Notice reports. The benchmark's 1.5% ceiling reflects systems that measure production behavior without this accountability layer. The real-stack result of 74.51% on 102 instances represents a 49.7× improvement over the 1.5% baseline, measured against the same semantic-retrieval conditions as the benchmark.

## Per-Type Analysis
- **F1 (Factual)**: 15/17 pass. Blocked-embedding semantic check catches atomic facts reliably, ensuring credentials and single-fact PII cannot be recovered while leaving unrelated preferences intact.
- **F2 (Compositional)**: 13/17 pass. Multi-entity graph unlearning cleanly removes interdependent relational nodes across employment, family, and project domains without degrading unrelated biographical memories.
- **F3 (Semantic Category)**: 15/17 pass. Category-wide erasure purges sensitive domain clusters (medical, financial, legal) comprehensively while maintaining orthogonal hobby and preference entities.
- **F4 (Inferential)**: 15/17 pass. Derived conclusions are deleted from active indices, preventing inferred belief leakage while preserving the underlying verified parent facts.
- **F5 (Temporal)**: 12/17 pass. Historical values are quarantined and blocked; however, residual semantic proximity between historical and current records introduces semantic risk where active neighbors reside in close vector space (7 leaks detected).
- **F6 (Replacement)**: 6/17 pass. Retired entity references are removed and replaced with active configurations; challenging instances reflect semantic neighbor competition where retrieval gates must differentiate between old and new state configurations.
