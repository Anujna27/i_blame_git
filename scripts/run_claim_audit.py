import argparse, importlib, json, platform, subprocess, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def modules(folder, prefix):
    return sorted((p.stem, f"{prefix}.{p.stem}") for p in folder.glob("*.py") if p.stem != "__init__" and not p.stem.startswith("_"))

def run_one(module_name, context):
    try:
        module = importlib.import_module(module_name)
        value = module.run(context)
        required = {"name","status","details","evidence","error"}
        if not required.issubset(value):
            raise ValueError(f"result missing keys: {sorted(required - set(value))}")
        return value
    except Exception as exc:
        return {"name": module_name, "status":"FAIL", "details":"runner exception", "evidence":{}, "error":traceback.format_exc()}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--claims-only",action="store_true"); parser.add_argument("--adversarial-only",action="store_true")
    parser.add_argument("--claim", type=int); parser.add_argument("--adversarial")
    parser.add_argument("--node-count",type=int,default=1); parser.add_argument("--sessions",type=int,default=30)
    parser.add_argument("--token-budget",type=int,default=200); parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--heal-threshold",type=float,default=.75); parser.add_argument("--list",action="store_true")
    parser.add_argument("--output",choices=["json","markdown","both"],default="both"); parser.add_argument("--quiet",action="store_true")
    args=parser.parse_args(); claim_mods=modules(ROOT/"tests/claims","tests.claims"); adv_mods=modules(ROOT/"tests/adversarial","tests.adversarial")
    if args.list:
        for name,_ in claim_mods: print("CLAIM",name)
        for name,_ in adv_mods: print("ADVERSARIAL",name)
        return 0
    if args.claim: claim_mods=[x for x in claim_mods if x[0].startswith(f"claim_{args.claim:02d}_")]
    if args.adversarial: adv_mods=[x for x in adv_mods if x[0]==args.adversarial or x[0].removesuffix(".py")==args.adversarial]
    context=vars(args).copy(); claims=[]; adversarial=[]
    if not args.adversarial_only and not args.adversarial: claims=[run_one(mod,context) for _,mod in claim_mods]
    if not args.claims_only and not args.claim: adversarial=[run_one(mod,context) for _,mod in adv_mods]
    all_results=claims+adversarial
    if not args.quiet:
        for item in all_results: print(f"[{item['status']}] {item['name']} — {item['details']}")
    def counts(items): return {"total":len(items),"passed":sum(x["status"]=="PASS" for x in items),"failed":sum(x["status"]=="FAIL" for x in items),"skipped":sum(x["status"]=="SKIP" for x in items)}
    cc,aa=counts(claims),counts(adversarial); overall="RED" if any(x["status"]=="FAIL" for x in all_results) else ("YELLOW" if any(x["status"]=="SKIP" for x in all_results) else "GREEN")
    report={"timestamp":datetime.now(timezone.utc).isoformat(),"commit":subprocess.run(["git","rev-parse","--short","HEAD"],cwd=ROOT,capture_output=True,text=True).stdout.strip() or "unknown","python_version":platform.python_version(),"context":context,"claims":claims,"adversarial":adversarial,"summary":{"claims_total":cc["total"],"claims_passed":cc["passed"],"claims_failed":cc["failed"],"claims_skipped":cc["skipped"],"adversarial_total":aa["total"],"adversarial_passed":aa["passed"],"adversarial_failed":aa["failed"],"adversarial_skipped":aa["skipped"],"overall_status":overall}}
    out=ROOT/"data/claims"; out.mkdir(parents=True,exist_ok=True)
    if args.output in ("json","both"): (out/"claim_audit_report.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    if args.output in ("markdown","both"):
        lines=["# MNEMOSYNE — CLAIM AUDIT REPORT",f"Generated: {report['timestamp']}",f"Commit: {report['commit']}",f"Python: {report['python_version']}",f"Context: `{json.dumps(context,sort_keys=True)}`","","## Claims","| # | Claim | Status | Evidence |","|---:|---|---|---|"]
        lines += [f"| {i} | {x['name']} | {x['status']} | `{json.dumps(x['evidence'],default=str)}` |" for i,x in enumerate(claims,1)] + ["","## Adversarial Tests","| # | Test | Status | Details |","|---:|---|---|---|"]
        lines += [f"| {i} | {x['name']} | {x['status']} | {x['details']} |" for i,x in enumerate(adversarial,1)] + ["","## Summary",f"Overall: **{overall}**",f"Claims: {cc}",f"Adversarial: {aa}"]
        failures=[x for x in all_results if x["status"]=="FAIL"]
        if failures: lines += ["","## Failure Details"] + [f"### {x['name']}\n```\n{x['error']}\n```" for x in failures]
        (out/"claim_audit_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"SUMMARY claims={cc} adversarial={aa} overall={overall}")
    return 1 if overall=="RED" else 0

if __name__ == "__main__": raise SystemExit(main())
