# demo/demo_runner.py
# M1 owns sections 5 and 6 (delete+notice and export capsule).
# M4 owns the overall structure, sections 1-4 and 7-10.

import json
from pathlib import Path

def print_residual_risk_notice(report):
    from core.residual_risk import ResidualRiskReporter
    from rich.console import Console
    console = Console()
    console.rule("[bold red]SECTION 5 — DELETION & AUDIT")
    console.print(f"[yellow]Deleting node:[/yellow] {report.node_id}")
    console.print(f"[yellow]Verdict:[/yellow] [bold]{report.verdict}[/bold]")
    console.print("")
    console.print(ResidualRiskReporter().generate_notice(report))
    console.print("")
    console.print(f"[dim]Signature: {report.signature[:32]}...[/dim]")
    console.print("")

def print_exported_capsule(capsule_dict, capsule_path=None):
    from rich.console import Console
    console = Console()
    console.rule("[bold cyan]SECTION 6 — CAPSULE EXPORT")
    console.print(f"[yellow]Capsule ID:[/yellow] {capsule_dict.get('capsule_id', 'n/a')}")
    console.print(f"[yellow]Source agent:[/yellow] {capsule_dict.get('source_agent', 'n/a')}")
    console.print(f"[yellow]Total memory nodes:[/yellow] {len(capsule_dict.get('memory_nodes', []))}")
    audit = capsule_dict.get("deletion_audit", {})
    console.print(f"[yellow]Deleted nodes:[/yellow] {len(audit.get('deleted_nodes', []))}")
    console.print(f"[yellow]Invalidated children:[/yellow] {len(audit.get('invalidated_children', []))}")
    console.print(f"[yellow]Residual risk flags:[/yellow] {len(audit.get('residual_risk_flags', []))}")
    hash_chain = capsule_dict.get("hash_chain", {})
    integrity = hash_chain.get("integrity_verified", False)
    console.print(f"[yellow]Hash chain integrity:[/yellow] {'✅' if integrity else '❌'} {integrity}")
    if capsule_path: console.print(f"[dim]Saved to: {capsule_path}[/dim]")
    console.print(""); console.print("[dim]Full JSON preview (first 500 chars):[/dim]")
    console.print(json.dumps(capsule_dict, indent=2, default=str)[:500] + "..."); console.print("")

def save_notice_snapshot(report, path="data/demo_notice_snapshot.json"):
    from core.residual_risk import ResidualRiskReporter
    snapshot = {"node_id": report.node_id, "verdict": report.verdict,
                "notice": ResidualRiskReporter().generate_notice(report),
                "signature": report.signature}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return path

def load_notice_snapshot(path="data/demo_notice_snapshot.json"):
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))
