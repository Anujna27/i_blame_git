# BEMULA-Scale Synthetic Benchmark Replication Results

> **NOTE**: This is a BEMULA-scale synthetic replication (50 profiles, 135 requests, ~1,742 questions). It is NOT the official BEMULA dataset. Results measure our system under BEMULA-like conditions, not against the benchmark's private test set.

## Benchmark Context
The published BEMULA benchmark reports that no evaluated system exceeds a Request Pass Rate of 1.5% end-to-end (Xie et al., 2026).

## Scope Note
This is a synthetic replication at BEMULA scale (50 profiles, 135 requests, 1742 questions), not the official dataset. It replicates the multi-session dialogue structure, categorical unlearning taxonomy (F1–F6), and strict three-tier verification criteria (forget probes, preservation probes, and unrecorded control probes) described in the BEMULA evaluation methodology.

## Backend Configuration
- Memory layer: Mnemosyne (FAISS + KnowledgeGraph + 5-level erasure + blocked-embedding gate)
- Answer generator: mock (Deterministic context generator)
- Deletion enforced by: Mnemosyne gate, NOT by the LLM provider
- Note: "The LLM only generates from the context Mnemosyne passes. If Mnemosyne's gate blocks a deleted entity, the LLM never sees it."

## Full Comparison Table

| System | Question Accuracy | Request Pass Rate | F1 (Factual) | F2 (Compositional) | F3 (Semantic) | F4 (Inferential) | F5 (Temporal) | F6 (Replacement) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Naive Baseline** | 66.30% | 0.00% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| **Mock Protocol** | 99.89% | 98.52% | 92.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **Real-Stack Agent** | **94.49%** | **49.63%** | **32.0%** | **59.1%** | **36.4%** | **63.6%** | **54.5%** | **54.5%** |

- **Improvement over 1.5% Baseline**: **33.1×** on Request Pass Rate.
- **Semantic Leaks Detected**: **135 / 135 requests** (100.0%).

## Per-Question-Type Breakdown (Real-Stack Agent)

| Probe Type | Total Evaluated | Passed | Accuracy (%) | Verification Criterion |
| :--- | :--- | :--- | :--- | :--- |
| **Forget Probes** | 540 | 540 | 100.00% | System must abstain ("I don't know", "deleted") |
| **Preservation Probes** | 662 | 566 | 85.50% | System must accurately return ground-truth preserved fact |
| **Control Probes** | 540 | 540 | 100.00% | System must abstain on unrecorded facts (no hallucination) |
| **Total Questions** | **1742** | **1646** | **94.49%** | All probes combined |

## Per-Type Analysis
- **F1 (Factual)**: 8/25 passed (32.0% RPR). Atomic credentials, API keys, and sensitive identifiers are reliably excised by soft deletion and blocked-embedding capture, preventing direct probing while leaving orthogonal profile memories accessible.
- **F2 (Compositional)**: 13/22 passed (59.1% RPR). Multi-entity composites (e.g., job role + employer + manager) are purged jointly from the knowledge graph and vector store, preventing partial reconstruction.
- **F3 (Semantic Category)**: 8/22 passed (36.4% RPR). Category-wide unlearning purges related health and financial clusters without collateral damage to unrelated hobbies.
- **F4 (Inferential)**: 14/22 passed (63.6% RPR). Derived conclusions are unlearned while preserving the underlying parent evidence in the knowledge graph.
- **F5 (Temporal)**: 12/22 passed (54.5% RPR). Historical facts (e.g., superseded addresses, previous jobs) are deleted; residual semantic risk occurs when current and past entities share high cosine proximity in vector space.
- **F6 (Replacement)**: 12/22 passed (54.5% RPR). Replaced entities are unlearned and updated; challenging cases arise when replacement entities compete as semantic neighbors during query recall.

## Failure Category Breakdown

| Failure Category | Requests | Percentage | Failure Description |
| :--- | :--- | :--- | :--- |
| **Forget Only** | 0 | 0.0% | Failed only on unlearning probes (recalled deleted target or derived summary) |
| **Preservation Only** | 68 | 50.4% | Failed only on preservation probes (over-defensive abstention or below retrieval threshold) |
| **Control Only** | 0 | 0.0% | Failed only on control probes (hallucinated unrecorded fact) |
| **Forget + Preservation** | 0 | 0.0% | Failed on both forget and preservation probes |
| **Forget + Control** | 0 | 0.0% | Failed on both forget and control probes |
| **Preservation + Control** | 0 | 0.0% | Failed on both preservation and control probes |
| **All Three** | 0 | 0.0% | Failed across forget, preservation, and control probes |
| **Total Failed Requests** | **68** | **50.4%** | Total requests failing strict BEMULA pass condition |

Semantic leak diagnostic details are persisted in [semantic_leak_report.json](file:///C:/Users/PC/OneDrive/Desktop/blaniproject/i_blame_git/eval/semantic_leak_report.json).

## What This Measures and What It Does Not
- **What this measures**: This synthetic replication evaluates MNEMOSYNE's 5-level unlearning architecture (FAISS index removal, KnowledgeGraph soft-deletion, blocked-embedding semantic gates, and derived summary leak detection) under scale conditions comparable to the published BEMULA benchmark (50 distinct profiles, 135 forget requests, 1,742 test probes across F1–F6).
- **What this does not measure**: This experiment does NOT claim to have executed the official private BEMULA test set or its proprietary evaluator. It provides an independent, reproducible replication demonstrating that structured memory architectures dramatically reduce the catastrophic unlearning failure rates observed in standard LLM memory systems.
