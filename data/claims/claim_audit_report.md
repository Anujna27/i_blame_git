# MNEMOSYNE — CLAIM AUDIT REPORT
Generated: 2026-11-12T19:44:19.242478+00:00
Commit: 316f12d
Python: 3.14.6
Context: `{"adversarial": null, "adversarial_only": false, "claim": null, "claims_only": false, "heal_threshold": 0.75, "list": false, "node_count": 1, "output": "both", "quiet": true, "seed": 42, "sessions": 30, "token_budget": 200}`

## Claims
| # | Claim | Status | Evidence |
|---:|---|---|---|
| 1 | Five-level erasure runs correctly on all scenarios | PASS | `{"levels": 5, "verdict": "partially_deleted"}` |
| 2 | Deletion state survives restart | PASS | `{"parent_state": "source_removed", "child_state": "invalidated", "hash_ok": true}` |
| 3 | Hash chain detects tampering | PASS | `{"original_ok": true, "post_tamper_ok": false}` |
| 4 | Capsule export preserves deletion state | PASS | `{"parent_blocked": true, "child_state": "invalidated"}` |
| 5 | Capsule import preserves residual risks | PASS | `{"original_risk_count": 1, "imported_risk_count": 1, "match": true}` |
| 6 | Session commit auto-triggers healing | PASS | `{"isolated_before": 1, "isolated_after": 1, "quarantined": 1}` |
| 7 | Vector retrieval respects trust filter | PASS | `{"verified_rank": 0, "planted_returned": true}` |
| 8 | Token budget is respected | PASS | `{"budget": 200, "actual_tokens": 100}` |
| 9 | Contradiction detection returns both nodes | PASS | `{"conflict_detected": true}` |
| 10 | Abstention triggers on insufficient evidence | PASS | `{"abstained": true, "reason": "I don't have verified information about unknown fact. No relevant memories were retrieved."}` |
| 11 | Lifecycle audit records who/what/when/why | PASS | `{"entry": {"entry_id": "b017bb00-f74e-4a1d-9224-622d2b1291ad", "event_id": "b017bb00-f74e-4a1d-9224-622d2b1291ad", "operation": "deletion_completed", "node_id": "69c45427-7569-4258-8a4d-758fb1afa722", "entity_id": "69c45427-7569-4258-8a4d-758fb1afa722", "actor": "agent", "reason": "erasure_request", "metadata": {}, "details": {"verdict": "fully_deleted", "signature": "b1a5ac1e2f9fc99e1001f26403a746492df6e1a3bdbcff27d4504d4deb36bbd4", "actor": "alice", "reason": "GDPR request", "content_digest": "b19b2022fbca5eebe2f23af94ff755f30bbd176d59e5e1c746e11b0adde61a7a", "content_redacted": true}, "prev_hash": "b4aa1f5d8aaf7e6742a86e5f0f06bc4e6e43beca3e17a5f438e5a1c136243293", "timestamp": "2026-11-12T19:44:18.325524+00:00", "hash": "e87b8a1cffdd0333348cc5b6416ffe60523e2ffda0e3a6d81cd60c41bbba6b4f"}, "has_actor": true, "has_reason": true, "has_timestamp": true}` |
| 12 | Legacy capsules import correctly | PASS | `{"import_ok": true, "node_count": 1, "errors": []}` |
| 13 | 30 sessions survive restart | PASS | `{"sessions_written": 30, "sessions_reloaded": 30, "hash_ok": true}` |
| 14 | Cross-agent hand-over mid-task preserves task state | PASS | `{"task_context_preserved": true, "memories_preserved": 2, "deleted_blocked": true}` |

## Adversarial Tests
| # | Test | Status | Details |
|---:|---|---|---|
| 1 | Adversarial: Import broken capsule | PASS | broken capsule rejected |
| 2 | Adversarial: Delete missing node | PASS | missing deletion checked |
| 3 | Adversarial: Delete twice | PASS | double deletion checked |
| 4 | Contradiction detection returns both nodes | PASS | contradiction engine checked |
| 5 | Abstention triggers on insufficient evidence | PASS | I don't have verified information about unknown fact. No relevant memories were retrieved. |
| 6 | Vector retrieval respects trust filter | PASS | trust ordering checked |
| 7 | Abstention triggers on insufficient evidence | PASS | I don't have verified information about unknown fact. No relevant memories were retrieved. |
| 8 | Deletion state survives restart | PASS | reload checked |
| 9 | Hash chain detects tampering | PASS | in-memory tamper checked |
| 10 | Token budget is respected | PASS | bounded active context checked |

## Summary
Overall: **GREEN**
Claims: {'total': 14, 'passed': 14, 'failed': 0, 'skipped': 0}
Adversarial: {'total': 10, 'passed': 10, 'failed': 0, 'skipped': 0}
