# MNEMOSYNE — CLAIM AUDIT REPORT
Generated: 2026-11-12T18:47:22.953555+00:00
Commit: f7abc9a
Python: 3.14.6
Context: `{"adversarial": null, "adversarial_only": false, "claim": null, "claims_only": false, "heal_threshold": 0.75, "list": false, "node_count": 1, "output": "both", "quiet": true, "seed": 42, "sessions": 30, "token_budget": 200}`

## Claims
| # | Claim | Status | Evidence |
|---:|---|---|---|
| 1 | Five-level erasure runs correctly on all scenarios | PASS | `{"levels": 5, "verdict": "partially_deleted"}` |
| 2 | Deletion state survives restart | PASS | `{"parent_state": "source_removed", "child_state": "invalidated", "hash_ok": true}` |
| 3 | Hash chain detects tampering | PASS | `{"original_ok": true, "post_tamper_ok": false}` |
| 4 | Capsule export preserves deletion state | SKIP | `{}` |
| 5 | Capsule import preserves residual risks | SKIP | `{}` |
| 6 | Session commit auto-triggers healing | PASS | `{"isolated_before": 1, "isolated_after": 1, "quarantined": 1}` |
| 7 | Vector retrieval respects trust filter | PASS | `{"verified_rank": 0, "planted_returned": true}` |
| 8 | Token budget is respected | PASS | `{"budget": 200, "actual_tokens": 100}` |
| 9 | Contradiction detection returns both nodes | PASS | `{"conflict_detected": true}` |
| 10 | Abstention triggers on insufficient evidence | PASS | `{"abstained": true, "reason": "I don't have verified information about unknown fact. No relevant memories were retrieved."}` |
| 11 | Lifecycle audit records who/what/when/why | PASS | `{"entry": {"entry_id": "7d22a47e-c3c8-4c80-8873-f649803fa0c4", "event_id": "7d22a47e-c3c8-4c80-8873-f649803fa0c4", "operation": "deletion_completed", "node_id": "d45c8157-49dc-4065-91e3-73465a43fd0a", "entity_id": "d45c8157-49dc-4065-91e3-73465a43fd0a", "actor": "agent", "reason": "erasure_request", "metadata": {}, "details": {"verdict": "fully_deleted", "signature": "bed2c91129871d30b0a19c32b9fc0f59c53d21ff46889c78aedf9c6c9005b9cc", "actor": "alice", "reason": "GDPR request"}, "prev_hash": "af00ee2cb81762ac798e1aa31f4f38dbf483badda33a6c35172a7d9f34c90433", "timestamp": "2026-11-12T18:47:22.168384+00:00", "hash": "ce4d903e921470de1a7fd4344fa7b57265301a26d2e090712551ec95b9c1ecb1"}, "has_actor": true, "has_reason": true, "has_timestamp": true}` |
| 12 | Legacy capsules import correctly | SKIP | `{}` |
| 13 | 30 sessions survive restart | PASS | `{"sessions_written": 30, "sessions_reloaded": 30, "hash_ok": true}` |
| 14 | Cross-agent hand-over mid-task preserves task state | SKIP | `{}` |

## Adversarial Tests
| # | Test | Status | Details |
|---:|---|---|---|
| 1 | Adversarial: Import broken capsule | SKIP | Requires isolated capsule fixture |
| 2 | Adversarial: Delete missing node | SKIP | Requires adversarial mock-store harness |
| 3 | Adversarial: Delete twice | SKIP | Requires adversarial mock-store harness |
| 4 | Contradiction detection returns both nodes | PASS | contradiction engine checked |
| 5 | Abstention triggers on insufficient evidence | PASS | I don't have verified information about unknown fact. No relevant memories were retrieved. |
| 6 | Vector retrieval respects trust filter | PASS | trust ordering checked |
| 7 | Abstention triggers on insufficient evidence | PASS | I don't have verified information about unknown fact. No relevant memories were retrieved. |
| 8 | Deletion state survives restart | PASS | reload checked |
| 9 | Hash chain detects tampering | PASS | in-memory tamper checked |
| 10 | Token budget is respected | PASS | bounded active context checked |

## Summary
Overall: **YELLOW**
Claims: {'total': 14, 'passed': 10, 'failed': 0, 'skipped': 4}
Adversarial: {'total': 10, 'passed': 7, 'failed': 0, 'skipped': 3}
