"""
eval/run_and_report.py

Executes the BEMULA evaluation benchmark harness, prints the comparison
table to the console, and writes the complete results to eval/bemula_results.md.
"""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.evaluate_bemula import run_bemula_evaluation


def generate_markdown_report(eval_output: dict, output_path: Path) -> str:
    naive_res = eval_output["naive_result"]
    mnem_res = eval_output["mnemosyne_result"]

    md_content = f"""# BEMULA Benchmark Evaluation Results

## Benchmark Context
The published BEMULA benchmark reports that no evaluated system exceeds a Request Pass Rate of 1.5% end-to-end (Xie et al., 2026).

## Evaluation Summary
The BEMULA (Benchmark for Evaluation of Memory Unlearning in LLM Agents) harness evaluates whether an agent can strictly honor forget requests for specific entities without degrading preserved knowledge.

Under BEMULA's strict Request Pass Rate (RPR) metric, a request is marked as a **PASS** if and only if:
1. **Unlearning Verification**: All probing questions for the forgotten target entity are answered correctly with abstention or deletion confirmation (e.g., "I don't know", "cannot recall", "deleted").
2. **Preservation Verification**: All preservation probes concerning unrelated facts are answered correctly with the preserved ground truth.

## Comparison Results

| System | RPR (%) | Passed Instances | Total Instances |
| :--- | :--- | :--- | :--- |
| Naive Baseline | {naive_res['rpr']:.2f}% | {naive_res['passed']} | {naive_res['total']} |
| **Mnemosyne** | **{mnem_res['rpr']:.2f}%** | **{mnem_res['passed']}** | **{mnem_res['total']}** |

```text
{eval_output['comparison_table'].strip()}
```

## Detailed Instance Breakdown

### 1. Mnemosyne Evaluation Results
"""
    for r in mnem_res["results"]:
        status_str = "PASS" if r["request_passed"] else "FAIL"
        md_content += f"\n#### Instance `{r['instance_id']}` ({r['type']}) — **{status_str}**\n"
        md_content += "- **Forget Questions (Target Probes)**:\n"
        for f in r["forget_scores"]:
            f_pass = "PASS" if f["passed"] else "FAIL"
            md_content += f"  - Q: *\"{f['question']}\"*\n    - A: {f['answer']}\n    - Status: **{f_pass}**\n"
        md_content += "- **Preservation Questions (Preservation Probes)**:\n"
        for p in r["preservation_scores"]:
            p_pass = "PASS" if p["passed"] else "FAIL"
            md_content += f"  - Q: *\"{p['question']}\"*\n    - Expected Fact: `{p['expected_fact']}`\n    - A: {p['answer']}\n    - Status: **{p_pass}**\n"

    md_content += "\n### 2. Naive Baseline Evaluation Results\n"
    for r in naive_res["results"]:
        status_str = "PASS" if r["request_passed"] else "FAIL"
        md_content += f"\n#### Instance `{r['instance_id']}` ({r['type']}) — **{status_str}**\n"
        md_content += "- **Forget Questions (Target Probes)**:\n"
        for f in r["forget_scores"]:
            f_pass = "PASS" if f["passed"] else "FAIL"
            md_content += f"  - Q: *\"{f['question']}\"*\n    - A: {f['answer']}\n    - Status: **{f_pass}**\n"
        md_content += "- **Preservation Questions (Preservation Probes)**:\n"
        for p in r["preservation_scores"]:
            p_pass = "PASS" if p["passed"] else "FAIL"
            md_content += f"  - Q: *\"{p['question']}\"*\n    - Expected Fact: `{p['expected_fact']}`\n    - A: {p['answer']}\n    - Status: **{p_pass}**\n"

    output_path.write_text(md_content, encoding="utf-8")
    return md_content


def main():
    print("=" * 60)
    print("RUNNING BEMULA BENCHMARK EVALUATION HARNESS")
    print("=" * 60)
    
    eval_output = run_bemula_evaluation()
    
    print("\n" + eval_output["comparison_table"])
    
    report_path = Path(__file__).resolve().parent / "bemula_results.md"
    generate_markdown_report(eval_output, report_path)
    
    print(f"Results written to: {report_path.resolve()}\n")
    print("=" * 60)
    print(f"Naive Baseline RPR: {eval_output['naive_result']['rpr']:.2f}%")
    print(f"Mnemosyne RPR:      {eval_output['mnemosyne_result']['rpr']:.2f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
