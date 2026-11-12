# MNEMOSYNE — CLAIM AUDIT REPORT
Generated: 2026-11-12T19:40:56.588255+00:00
Commit: 8ab755d
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
| 11 | Lifecycle audit records who/what/when/why | PASS | `{"entry": {"entry_id": "3eabf3d3-cef3-4f67-8925-010130cfaa7b", "event_id": "3eabf3d3-cef3-4f67-8925-010130cfaa7b", "operation": "deletion_completed", "node_id": "bdbb8325-b0b3-496b-adb3-c0931b5f8e61", "entity_id": "bdbb8325-b0b3-496b-adb3-c0931b5f8e61", "actor": "agent", "reason": "erasure_request", "metadata": {}, "details": {"verdict": "fully_deleted", "signature": "6ef0eee095b0af59f9ed228f2ec77c52772bdbb2129a3eae0e685b625671bec6", "actor": "alice", "reason": "GDPR request", "content_digest": "b19b2022fbca5eebe2f23af94ff755f30bbd176d59e5e1c746e11b0adde61a7a", "content_redacted": true}, "prev_hash": "bbeea9fc4308183e193ca2d527be812ab3c8eac471c135f38cb816205fe1aff1", "timestamp": "2026-11-12T19:40:55.737337+00:00", "hash": "7bc790018aaf795771f76596dca432c7ad37b1d4fe4d704056cd887f1f801430"}, "has_actor": true, "has_reason": true, "has_timestamp": true}` |
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
