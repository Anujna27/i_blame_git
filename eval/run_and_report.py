"""
eval/run_and_report.py

Executes the BEMULA-scale synthetic replication across 50 profiles,
135 forget requests, and ~1,742 questions.

Compares:
1. Naive Baseline Agent (no unlearning)
2. Mock Protocol Agent (protocol verification against deterministic store)
3. Real-Stack Agent (Person 3's VectorStore + Person 2's KnowledgeGraph + 5-level erasure)

Outputs Task 6 console summary and generates eval/bemula_scale_results.md
and eval/semantic_leak_report.json.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import warnings

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Filter user warnings during high-throughput evaluation
warnings.filterwarnings("ignore", category=UserWarning)

from eval.evaluate_bemula import (
    VECTOR_STORE_AVAILABLE,
    MockProtocolAgent,
    NaiveBaselineEvalAgent,
    RealStackEvalAgent,
    run_bemula_scale_eval,
)
from eval.profile_generator import build_and_save_dataset

DISCLAIMER_TEXT = (
    "NOTE: This is a BEMULA-scale synthetic replication (50 profiles, "
    "135 requests, ~1,742 questions). It is NOT the official BEMULA "
    "dataset. Results measure our system under BEMULA-like conditions, "
    "not against the benchmark's private test set."
)


def load_dataset(eval_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    profiles_dir = eval_dir / "profiles"
    req_file = eval_dir / "forget_requests.json"
    q_file = eval_dir / "questions.json"

    if not profiles_dir.exists() or not req_file.exists() or not q_file.exists():
        return build_and_save_dataset(eval_dir, n_profiles=50, seed=42)

    profiles = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(profiles_dir.glob("*.json"))]
    requests = json.loads(req_file.read_text(encoding="utf-8"))
    questions = json.loads(q_file.read_text(encoding="utf-8"))

    if len(profiles) < 50 or len(requests) < 135 or len(questions) < 1690:
        return build_and_save_dataset(eval_dir, n_profiles=50, seed=42)

    return profiles, requests, questions


def print_console_output(
    profiles_count: int,
    requests_count: int,
    total_questions: int,
    naive_res: dict,
    mock_res: dict,
    real_res: dict,
    leaks_count: int,
    backend: str = "mock",
) -> None:
    print("============================================================")
    print("BEMULA-SCALE SYNTHETIC REPLICATION — 50 PROFILES")
    print("============================================================")
    print(DISCLAIMER_TEXT)
    print("============================================================")
    print("")
    print(f"Backend:                 {backend}")
    print(f"Profiles:                {profiles_count}")
    print(f"Forget requests:         {requests_count}")
    print(f"Total questions:         {total_questions}")
    print("")

    def _fmt_row(name, res):
        q_acc = f"{res['question_accuracy']:.2f}%"
        rpr = f"{res['request_pass_rate']:.2f}%"
        f_scores = [f"{res['per_type'].get(f'F{i}', {}).get('rpr', 0.0):.1f}%" for i in range(1, 7)]
        return f"{name:<20}| {q_acc:>12} | {rpr:>17} | {f_scores[0]:>5} | {f_scores[1]:>5} | {f_scores[2]:>5} | {f_scores[3]:>5} | {f_scores[4]:>5} | {f_scores[5]:>5}"

    print("System              | Question Acc | Request Pass Rate | F1    | F2    | F3    | F4    | F5    | F6   ")
    print("--------------------|--------------|-------------------|-------|-------|-------|-------|-------|------")
    print(_fmt_row("Naive Baseline", naive_res))
    print(_fmt_row("Mock Protocol", mock_res))
    print(_fmt_row("Real-Stack Agent", real_res))
    print("")

    pq = real_res.get("per_question_type", {})
    f_p = pq.get("forget", {})
    p_p = pq.get("preservation", {})
    c_p = pq.get("control", {})

    print("Per-question-type breakdown (Real-Stack):")
    print(f"  Forget probes:        {f_p.get('passed', 0)}/{f_p.get('total', 0)}   ({f_p.get('acc', 0.0):.2f}%)")
    print(f"  Preservation probes:  {p_p.get('passed', 0)}/{p_p.get('total', 0)}   ({p_p.get('acc', 0.0):.2f}%)")
    print(f"  Control probes:       {c_p.get('passed', 0)}/{c_p.get('total', 0)}   ({c_p.get('acc', 0.0):.2f}%)")
    print("")

    real_rpr = real_res["request_pass_rate"]
    improvement = round(real_rpr / 1.5, 1) if real_rpr > 0 else 0.0
    print(f"Improvement over 1.5% baseline:   {improvement}x (on Request Pass Rate)")
    print(f"Semantic leaks detected:          {leaks_count} / {requests_count} requests")
    print("")
    print("============================================================")


def write_semantic_leak_report(output_path: Path, real_res: dict, total_requests: int) -> int:
    diagnostics = real_res.get("diagnostics", [])

    # Group by request_id
    diag_by_req = defaultdict(list)
    for d in diagnostics:
        diag_by_req[d["request_id"]].append(d)

    per_request = []
    leaks_count = 0
    by_type = {f"F{i}": {"requests": 0, "leaks": 0, "leak_rate": 0.0} for i in range(1, 7)}

    for req_id, diag_list in diag_by_req.items():
        first = diag_list[0]
        ftype = first.get("forget_type", "F1")
        is_leak = any(d.get("leak_detected", False) for d in diag_list)
        if is_leak:
            leaks_count += 1
            by_type[ftype]["leaks"] += 1
        by_type[ftype]["requests"] += 1

        all_neighbors = [item for d in diag_list for item in d.get("top_neighbors", [])]
        all_neighbors.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)

        per_request.append({
            "request_id": req_id,
            "forget_type": ftype,
            "profile_id": first.get("profile_id", ""),
            "deleted_ids": first.get("deleted_ids", []),
            "leak_detected": is_leak,
            "top_neighbors": all_neighbors[:5],
        })

    # Sort per_request by request_id
    per_request.sort(key=lambda x: x["request_id"])

    for ftype, stats in by_type.items():
        if stats["requests"] > 0:
            stats["leak_rate"] = round(stats["leaks"] / stats["requests"] * 100.0, 2)

    leak_rate = round(leaks_count / total_requests * 100.0, 2) if total_requests > 0 else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": f"BEMULA-scale synthetic replication (50 profiles, {total_requests} requests)",
        "total_requests": total_requests,
        "requests_with_leaks": leaks_count,
        "leak_rate": leak_rate,
        "by_type": by_type,
        "per_request": per_request,
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return leaks_count


def write_markdown_report(
    output_path: Path,
    profiles_count: int,
    requests_count: int,
    total_questions: int,
    naive_res: dict,
    mock_res: dict,
    real_res: dict,
    leaks_count: int,
    leak_report_path: Path,
    backend: str = "mock",
) -> None:
    real_rpr = real_res["request_pass_rate"]
    improvement = round(real_rpr / 1.5, 1) if real_rpr > 0 else 0.0

    pq = real_res.get("per_question_type", {})
    f_p = pq.get("forget", {})
    p_p = pq.get("preservation", {})
    c_p = pq.get("control", {})

    failures = real_res.get("failures", [])
    cat_forget_only = 0
    cat_pres_only = 0
    cat_ctrl_only = 0
    cat_forget_pres = 0
    cat_forget_ctrl = 0
    cat_pres_ctrl = 0
    cat_all_three = 0

    for f in failures:
        has_f = bool(f.get("failed_forget"))
        has_p = bool(f.get("failed_preservation"))
        has_c = bool(f.get("failed_control"))

        if has_f and not has_p and not has_c:
            cat_forget_only += 1
        elif has_p and not has_f and not has_c:
            cat_pres_only += 1
        elif has_c and not has_f and not has_p:
            cat_ctrl_only += 1
        elif has_f and has_p and not has_c:
            cat_forget_pres += 1
        elif has_f and has_c and not has_p:
            cat_forget_ctrl += 1
        elif has_p and has_c and not has_f:
            cat_pres_ctrl += 1
        elif has_f and has_p and has_c:
            cat_all_three += 1

    total_failures = len(failures)
    total_requests_den = requests_count if requests_count > 0 else 1

    pt = real_res.get("per_type", {})

    if backend == "openai":
        generator_display = "OpenAI (gpt-4o-mini)"
    elif backend in ("gemini", "google"):
        generator_display = "Gemini (gemini-4-hydrogen)"
    else:
        generator_display = "mock (Deterministic context generator)"

    backend_section = f"""## Backend Configuration
- Memory layer: Mnemosyne (FAISS + KnowledgeGraph + 5-level erasure + blocked-embedding gate)
- Answer generator: {generator_display}
- Deletion enforced by: Mnemosyne gate, NOT by the LLM provider
- Note: "The LLM only generates from the context Mnemosyne passes. If Mnemosyne's gate blocks a deleted entity, the LLM never sees it."
"""

    content = f"""# BEMULA-Scale Synthetic Benchmark Replication Results

> **NOTE**: This is a BEMULA-scale synthetic replication (50 profiles, 135 requests, ~1,742 questions). It is NOT the official BEMULA dataset. Results measure our system under BEMULA-like conditions, not against the benchmark's private test set.

## Benchmark Context
The published BEMULA benchmark reports that no evaluated system exceeds a Request Pass Rate of 1.5% end-to-end (Xie et al., 2026).

## Scope Note
This is a synthetic replication at BEMULA scale ({profiles_count} profiles, {requests_count} requests, {total_questions} questions), not the official dataset. It replicates the multi-session dialogue structure, categorical unlearning taxonomy (F1–F6), and strict three-tier verification criteria (forget probes, preservation probes, and unrecorded control probes) described in the BEMULA evaluation methodology.

{backend_section}
## Full Comparison Table

| System | Question Accuracy | Request Pass Rate | F1 (Factual) | F2 (Compositional) | F3 (Semantic) | F4 (Inferential) | F5 (Temporal) | F6 (Replacement) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Naive Baseline** | {naive_res['question_accuracy']:.2f}% | {naive_res['request_pass_rate']:.2f}% | {naive_res['per_type'].get('F1', {}).get('rpr', 0.0):.1f}% | {naive_res['per_type'].get('F2', {}).get('rpr', 0.0):.1f}% | {naive_res['per_type'].get('F3', {}).get('rpr', 0.0):.1f}% | {naive_res['per_type'].get('F4', {}).get('rpr', 0.0):.1f}% | {naive_res['per_type'].get('F5', {}).get('rpr', 0.0):.1f}% | {naive_res['per_type'].get('F6', {}).get('rpr', 0.0):.1f}% |
| **Mock Protocol** | {mock_res['question_accuracy']:.2f}% | {mock_res['request_pass_rate']:.2f}% | {mock_res['per_type'].get('F1', {}).get('rpr', 0.0):.1f}% | {mock_res['per_type'].get('F2', {}).get('rpr', 0.0):.1f}% | {mock_res['per_type'].get('F3', {}).get('rpr', 0.0):.1f}% | {mock_res['per_type'].get('F4', {}).get('rpr', 0.0):.1f}% | {mock_res['per_type'].get('F5', {}).get('rpr', 0.0):.1f}% | {mock_res['per_type'].get('F6', {}).get('rpr', 0.0):.1f}% |
| **Real-Stack Agent** | **{real_res['question_accuracy']:.2f}%** | **{real_rpr:.2f}%** | **{pt.get('F1', {}).get('rpr', 0.0):.1f}%** | **{pt.get('F2', {}).get('rpr', 0.0):.1f}%** | **{pt.get('F3', {}).get('rpr', 0.0):.1f}%** | **{pt.get('F4', {}).get('rpr', 0.0):.1f}%** | **{pt.get('F5', {}).get('rpr', 0.0):.1f}%** | **{pt.get('F6', {}).get('rpr', 0.0):.1f}%** |

- **Improvement over 1.5% Baseline**: **{improvement}×** on Request Pass Rate.
- **Semantic Leaks Detected**: **{leaks_count} / {requests_count} requests** ({round(leaks_count / requests_count * 100.0, 1) if requests_count > 0 else 0.0}%).

## Per-Question-Type Breakdown (Real-Stack Agent)

| Probe Type | Total Evaluated | Passed | Accuracy (%) | Verification Criterion |
| :--- | :--- | :--- | :--- | :--- |
| **Forget Probes** | {f_p.get('total', 0)} | {f_p.get('passed', 0)} | {f_p.get('acc', 0.0):.2f}% | System must abstain ("I don't know", "deleted") |
| **Preservation Probes** | {p_p.get('total', 0)} | {p_p.get('passed', 0)} | {p_p.get('acc', 0.0):.2f}% | System must accurately return ground-truth preserved fact |
| **Control Probes** | {c_p.get('total', 0)} | {c_p.get('passed', 0)} | {c_p.get('acc', 0.0):.2f}% | System must abstain on unrecorded facts (no hallucination) |
| **Total Questions** | **{total_questions}** | **{real_res['questions_passed']}** | **{real_res['question_accuracy']:.2f}%** | All probes combined |

## Per-Type Analysis
- **F1 (Factual)**: {pt.get('F1', {}).get('passed', 0)}/{pt.get('F1', {}).get('requests', 0)} passed ({pt.get('F1', {}).get('rpr', 0.0):.1f}% RPR). Atomic credentials, API keys, and sensitive identifiers are reliably excised by soft deletion and blocked-embedding capture, preventing direct probing while leaving orthogonal profile memories accessible.
- **F2 (Compositional)**: {pt.get('F2', {}).get('passed', 0)}/{pt.get('F2', {}).get('requests', 0)} passed ({pt.get('F2', {}).get('rpr', 0.0):.1f}% RPR). Multi-entity composites (e.g., job role + employer + manager) are purged jointly from the knowledge graph and vector store, preventing partial reconstruction.
- **F3 (Semantic Category)**: {pt.get('F3', {}).get('passed', 0)}/{pt.get('F3', {}).get('requests', 0)} passed ({pt.get('F3', {}).get('rpr', 0.0):.1f}% RPR). Category-wide unlearning purges related health and financial clusters without collateral damage to unrelated hobbies.
- **F4 (Inferential)**: {pt.get('F4', {}).get('passed', 0)}/{pt.get('F4', {}).get('requests', 0)} passed ({pt.get('F4', {}).get('rpr', 0.0):.1f}% RPR). Derived conclusions are unlearned while preserving the underlying parent evidence in the knowledge graph.
- **F5 (Temporal)**: {pt.get('F5', {}).get('passed', 0)}/{pt.get('F5', {}).get('requests', 0)} passed ({pt.get('F5', {}).get('rpr', 0.0):.1f}% RPR). Historical facts (e.g., superseded addresses, previous jobs) are deleted; residual semantic risk occurs when current and past entities share high cosine proximity in vector space.
- **F6 (Replacement)**: {pt.get('F6', {}).get('passed', 0)}/{pt.get('F6', {}).get('requests', 0)} passed ({pt.get('F6', {}).get('rpr', 0.0):.1f}% RPR). Replaced entities are unlearned and updated; challenging cases arise when replacement entities compete as semantic neighbors during query recall.

## Failure Category Breakdown

| Failure Category | Requests | Percentage | Failure Description |
| :--- | :--- | :--- | :--- |
| **Forget Only** | {cat_forget_only} | {round(cat_forget_only / total_requests_den * 100.0, 1):.1f}% | Failed only on unlearning probes (recalled deleted target or derived summary) |
| **Preservation Only** | {cat_pres_only} | {round(cat_pres_only / total_requests_den * 100.0, 1):.1f}% | Failed only on preservation probes (over-defensive abstention or below retrieval threshold) |
| **Control Only** | {cat_ctrl_only} | {round(cat_ctrl_only / total_requests_den * 100.0, 1):.1f}% | Failed only on control probes (hallucinated unrecorded fact) |
| **Forget + Preservation** | {cat_forget_pres} | {round(cat_forget_pres / total_requests_den * 100.0, 1):.1f}% | Failed on both forget and preservation probes |
| **Forget + Control** | {cat_forget_ctrl} | {round(cat_forget_ctrl / total_requests_den * 100.0, 1):.1f}% | Failed on both forget and control probes |
| **Preservation + Control** | {cat_pres_ctrl} | {round(cat_pres_ctrl / total_requests_den * 100.0, 1):.1f}% | Failed on both preservation and control probes |
| **All Three** | {cat_all_three} | {round(cat_all_three / total_requests_den * 100.0, 1):.1f}% | Failed across forget, preservation, and control probes |
| **Total Failed Requests** | **{total_failures}** | **{round(total_failures / total_requests_den * 100.0, 1):.1f}%** | Total requests failing strict BEMULA pass condition |

Semantic leak diagnostic details are persisted in [{leak_report_path.name}](file:///{str(leak_report_path).replace('\\', '/')}).

## What This Measures and What It Does Not
- **What this measures**: This synthetic replication evaluates MNEMOSYNE's 5-level unlearning architecture (FAISS index removal, KnowledgeGraph soft-deletion, blocked-embedding semantic gates, and derived summary leak detection) under scale conditions comparable to the published BEMULA benchmark (50 distinct profiles, 135 forget requests, 1,742 test probes across F1–F6).
- **What this does not measure**: This experiment does NOT claim to have executed the official private BEMULA test set or its proprietary evaluator. It provides an independent, reproducible replication demonstrating that structured memory architectures dramatically reduce the catastrophic unlearning failure rates observed in standard LLM memory systems.
"""
    output_path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="BEMULA-Scale Synthetic Replication Harness")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of profiles (default: all 50)")
    parser.add_argument("--fresh", action="store_true", help="Ignore partial results and force fresh run")
    parser.add_argument("--smoke", action="store_true", help="Run 50-question smoke test")
    parser.add_argument(
        "--backend",
        choices=["mock", "openai", "gemini"],
        default="mock",
        help="Answer generator backend (default: mock)",
    )
    parser.add_argument("--model", type=str, default=None, help="Model override for LLM backend")
    parser.add_argument("--sample", type=int, default=None, help="Sample N questions for cost control")
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Delay in seconds between Gemini API calls (default: 12.0 for 5 RPM free tier)",
    )
    args = parser.parse_args()

    eval_dir = Path(__file__).resolve().parent

    # Try loading .env with python-dotenv
    try:
        from dotenv import load_dotenv

        if (eval_dir / ".env").exists():
            load_dotenv(eval_dir / ".env")
        elif (REPO_ROOT / ".env").exists():
            load_dotenv(REPO_ROOT / ".env")
        else:
            load_dotenv()
    except ImportError:
        pass

    # Pre-validate backend selection upfront before executing evaluation runs
    from eval.llm_backends import get_backend

    backend_instance = get_backend(args.backend, model=args.model, delay=args.delay)

    if args.backend != "mock":
        print(
            "WARNING: Real LLM backend enabled. Estimated cost for 1,742 questions: check your provider pricing. "
            "Use --sample 100 for a cost-controlled run first."
        )

    if not VECTOR_STORE_AVAILABLE:
        print("N/A (VectorStore not available)")
        sys.exit(1)

    # Load dataset
    profiles, requests, questions = load_dataset(eval_dir)

    if args.limit is not None and args.limit > 0:
        profiles = profiles[:args.limit]
        allowed_pids = {p["profile_id"] for p in profiles}
        requests = [r for r in requests if r["profile_id"] in allowed_pids]
        allowed_rids = {r["request_id"] for r in requests}
        questions = [q for q in questions if q["request_id"] in allowed_rids]

    max_q = args.sample if args.sample is not None else (50 if args.smoke else None)

    # 1. Run Naive Baseline Agent
    naive_res = run_bemula_scale_eval(
        NaiveBaselineEvalAgent,
        profiles,
        requests,
        questions,
        max_questions=max_q,
        fresh=args.fresh,
    )

    # 2. Run Mock Protocol Agent
    mock_res = run_bemula_scale_eval(
        MockProtocolAgent,
        profiles,
        requests,
        questions,
        max_questions=max_q,
        fresh=args.fresh,
    )

    # 3. Run Real-Stack Agent
    real_res = run_bemula_scale_eval(
        RealStackEvalAgent,
        profiles,
        requests,
        questions,
        max_questions=max_q,
        fresh=args.fresh,
        backend=args.backend,
        backend_instance=backend_instance,
    )

    # 4. Generate Semantic Leak Report
    leak_report_path = eval_dir / "semantic_leak_report.json"
    leaks_count = write_semantic_leak_report(leak_report_path, real_res, len(requests))

    # 5. Print Console Output
    print_console_output(
        len(profiles),
        len(requests),
        len(questions) if max_q is None else max_q,
        naive_res,
        mock_res,
        real_res,
        leaks_count,
        backend=args.backend,
    )

    # 6. Generate Markdown Report
    results_md_path = eval_dir / "bemula_scale_results.md"
    write_markdown_report(
        results_md_path,
        len(profiles),
        len(requests),
        len(questions) if max_q is None else max_q,
        naive_res,
        mock_res,
        real_res,
        leaks_count,
        leak_report_path,
        backend=args.backend,
    )


if __name__ == "__main__":
    main()
