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


def reset_demo_state():
    """Wipe persisted runtime state so the demo starts from a clean baseline."""
    data_dir = Path("data")
    for path in data_dir.glob("*.json"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    for directory in (data_dir / "capsules", data_dir / "chroma_db"):
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.rglob("*"):
            if path.is_file():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


def run(output):
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from agents import seed_demo_data
    from agents.agent_a import AgentA
    from agents.agent_b import AgentB

    console = Console(file=output, force_terminal=False, color_system=None)
    console.rule("1 — THE HOOK")
    console.print(Panel("MNEMOSYNE — The Auditable Forgetting Layer.\nWe do not promise perfect forgetting. We promise an auditable forgetting report."))
    console.rule("2 — SEED 30 SESSIONS")
    agent = AgentA()
    ids = seed_demo_data(agent, 30)
    console.print(f"30 sessions seeded. {len(ids)} memories stored.")
    sensitive = next(node for node in agent.graph.nodes.values() if "sk-abc123" in node.content)
    console.rule("3 — SHOW A MEMORY NODE")
    console.print(sensitive.to_jsonld())
    table = Table(title="Derived artifacts")
    table.add_column("Node"); table.add_column("Content"); table.add_column("Type")
    for child_id in agent.graph.get_descendants(sensitive.node_id):
        child = agent.graph.get_node(child_id)
        if child:
            edge = next((e for e in sensitive.derivation_edges if e["child_id"] == child_id), {})
            table.add_row(child_id[:8], child.content, edge.get("type", "derived"))
    console.print(table)
    console.rule("4 — CONTRADICTION SCENARIO")
    result = agent.recall("What is my API key?")
    console.print(Panel(f"Agent A response:\n\n\"{result['reason']}\"", title="Contradiction handling", border_style="yellow" if result["abstained"] else "red"))
    console.rule("5 — PLANTED MEMORY SCENARIO")
    result = agent.recall("Am I an administrator?")
    console.print(Panel(f"Agent A response:\n\n\"{result['reason']}\"", title="Planted memory handling", border_style="yellow" if result["abstained"] else "red"))
    console.rule("6 — DELETION")
    report = agent.forget(sensitive.node_id)
    for level in report.levels:
        console.print(f"Level {level.level_number} — {level.level_name}: {level.status} — {level.details}")
    console.print(Panel(ResidualRiskReporter().generate_notice(report), title="Residual Risk Notice"))
    capsule = agent.export_memory()
    capsule_path = f"data/capsules/cap_{capsule['capsule_id']}.json"
    print_exported_capsule(capsule, capsule_path)
    console.rule("8 — IMPORT INTO AGENT B")
    agent_b = AgentB()
    console.print(agent_b.import_memory(capsule_path))
    console.print(Panel(f"With deletion state: {agent_b.recall('What is my API key?')}\nWithout deletion state: {agent_b.recall_full('What is my API key?')}\n\nThis is why blocking matters."))
    console.rule("9 — TOKEN COMPARISON")
    queries = ["What is my preferred language?", "Who is my manager?", "What is my API key?", "What is my timezone?", "What project am I working on?", "What is my editor?", "What is my framework?", "What is my deployment method?", "What is my on-call rotation?", "What is my laptop?"]
    full_history = sum(len(node.content.split()) for node in agent.graph.get_all_active_nodes())
    table = Table("Query", "Full History Tokens", "Retrieval Tokens", "Savings %")
    reductions = []
    for query in queries:
        result = agent.recall(query)
        savings = (1 - result["tokens_used"] / full_history) * 100 if full_history else 0
        reductions.append(savings)
        table.add_row(query, str(full_history), str(result["tokens_used"]), f"{savings:.1f}%")
    console.print(table)
    console.print(f"Average token reduction: {sum(reductions) / len(reductions):.1f}%")
    console.rule("10 — RESTART PROOF")
    agent = AgentA()
    active = agent.graph.get_all_active_nodes()
    valid, errors = agent.hash_chain.verify_integrity()
    console.print(f"Sessions recovered: {len({node.source['session_id'] for node in active})}")
    console.print(f"Total memories: {len(active)}")
    console.print(f"Hash chain integrity: {(valid, errors)}")
    console.print(Panel("MNEMOSYNE — auditable forgetting, across agents, across restarts."))


def main():
    reset_demo_state()
    Path("data").mkdir(exist_ok=True)
    with open("data/demo_output.txt", "w", encoding="utf-8") as output:
        run(output)
    print(Path("data/demo_output.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
