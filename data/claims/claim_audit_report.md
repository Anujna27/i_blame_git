# MNEMOSYNE — CLAIM AUDIT REPORT
Generated: 2026-11-12T19:30:28.508019+00:00
Commit: 9ba0448
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
| 11 | Lifecycle audit records who/what/when/why | PASS | `{"entry": {"entry_id": "4f0e97c9-484f-499e-b86a-6889a086b93a", "event_id": "4f0e97c9-484f-499e-b86a-6889a086b93a", "operation": "deletion_completed", "node_id": "37dffbb4-95b5-4a63-b1f4-5f814ec2ba19", "entity_id": "37dffbb4-95b5-4a63-b1f4-5f814ec2ba19", "actor": "agent", "reason": "erasure_request", "metadata": {}, "details": {"verdict": "fully_deleted", "signature": "11c160f5510a30315465d315d9e99e2c393aadcd5a0f58c860b1d8bc4324f443", "actor": "alice", "reason": "GDPR request", "content_digest": "b19b2022fbca5eebe2f23af94ff755f30bbd176d59e5e1c746e11b0adde61a7a", "content_redacted": true}, "prev_hash": "bb2b1c4c50687cfb3df7981b7baf4afb45114358759bc0912a69cfe966d6cbfe", "timestamp": "2026-11-12T19:30:27.751645+00:00", "hash": "890878cbf129bc45b1785975ab2b77dcea86322b58d89aa7f85c1aa476586037"}, "has_actor": true, "has_reason": true, "has_timestamp": true}` |
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
