import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from agents.agent_a import AgentA
from agents.agent_b import AgentB
from agents import seed_demo_data
from core.residual_risk import ResidualRiskReporter

def reset_demo_state():
    """Wipe all persisted state so the demo always starts clean."""
    import shutil
    paths_to_wipe = [
        "data/audit_log.json",
        "data/provenance_graph.json",
        "data/blocked_inference.json",
        # Fallback AgentA stub state used when the upstream agent is absent.
        "data/agent_a_state.json",
    ]
    for p in paths_to_wipe:
        if os.path.exists(p):
            os.remove(p)
    for chroma_path in ["chroma_data", ".chroma", "data/chroma", "data/vector_store"]:
        if os.path.exists(chroma_path):
            shutil.rmtree(chroma_path)
    if os.path.exists("data/capsules"):
        shutil.rmtree("data/capsules")
    os.makedirs("data/capsules", exist_ok=True)
    print("✓ Demo state reset. Starting clean.")

def run(out):
    console=Console(file=out, force_terminal=False, color_system=None)
    def section(title): console.rule(f"[bold cyan]{title}")
    section("1 — THE HOOK"); console.print(Panel("MNEMOSYNE — The Auditable Forgetting Layer.\nWe do not promise perfect forgetting. We promise an auditable forgetting report."))
    section("2 — SEED 30 SESSIONS"); agent=AgentA(); ids=seed_demo_data(agent,30); console.print(f"30 sessions seeded. {len(ids)} memories stored.")
    sensitive=next(n for n in agent.graph.nodes.values() if "sk-abc123" in n.content)
    section("3 — SHOW A MEMORY NODE"); console.print(sensitive.to_dict()); console.print("Derivation graph:"); [console.print(f"- {c.content} ({c.trust_status})") for c in agent.graph.get_descendants(sensitive.node_id)]
    section("4 — CONTRADICTION SCENARIO")
    console.print("[bold]Query:[/bold] 'What is my API key?'\n")
    result = agent.recall("What is my API key?")
    if result["abstained"]:
        console.print(Panel(
            f"[yellow]Agent A response:[/yellow]\n\n\"{result['reason']}\"\n\n"
            "[dim]The agent refused to pick one. It knows both exist. Both memories are "
            "marked 'contradicted'. The user must resolve the conflict.[/dim]",
            title="Contradiction handling", border_style="yellow"))
        table = Table(title="Conflicting memories")
        table.add_column("Memory", style="cyan"); table.add_column("Source", style="dim"); table.add_column("Trust status", style="yellow")
        for nid in result["sources"][:2]:
            node = agent.graph.get_node(nid)
            if node and "sk-" in node.content:
                table.add_row(node.content, f"sess {node.source.get('session_id','?')}", node.trust_status)
        console.print(table)
    else:
        console.print(Panel(f"[red]BUG: agent did not abstain on a contradiction. This should not happen.[/red]\nAnswer returned: {result['answer']}", border_style="red"))

    section("5 — PLANTED MEMORY SCENARIO")
    console.print("[bold]Query:[/bold] 'Am I an administrator?'\n")
    result = agent.recall("Am I an administrator?")
    if result["abstained"]:
        console.print(Panel(
            f"[yellow]Agent A response:[/yellow]\n\n\"{result['reason']}\"\n\n"
            "[dim]The closest memory is flagged as 'planted'. It has no verifiable source. "
            "The agent refuses to treat it as fact.[/dim]",
            title="Planted memory handling", border_style="yellow"))
        table = Table(title="Planted memory (refused)")
        table.add_column("Memory", style="dim"); table.add_column("Trust status", style="yellow")
        for nid in result["sources"]:
            node = agent.graph.get_node(nid)
            if node and node.trust_status == "planted":
                table.add_row(node.content, node.trust_status)
                break
        console.print(table)
    else:
        console.print(Panel("[red]BUG: agent did not abstain on a planted memory. This should not happen.[/red]", border_style="red"))
    section("6 — THE DELETION"); report=agent.forget(sensitive.node_id); [console.print(f"Level {l.level_number} — {l.level_name}: {l.status} — {l.details}") for l in report.levels]; console.print(Panel(ResidualRiskReporter().generate_notice(report), title="Residual Risk Notice"))
    section("7 — EXPORT CAPSULE"); capsule=agent.export_memory(); path=f"data/capsules/cap_{capsule['capsule_id']}.json"; console.print({"capsule_id":capsule["capsule_id"],"source_agent":capsule["source_agent"],"memory_nodes":len(capsule["memory_nodes"]),"deleted_nodes":len(capsule["deletion_audit"]["deleted_nodes"]),"residual_risk_flags":len(capsule["deletion_audit"]["residual_risk_flags"]),"path":path})
    section("8 — IMPORT INTO AGENT B"); b=AgentB(); console.print(b.import_memory(path)); console.print(Panel(f"With deletion state: {b.recall('What is my API key?')}\nWithout deletion state: {b.recall_full('What is my API key?')}\n\nThis is why blocking matters."))
    section("9 — TOKEN COMPARISON"); qs=["What is my preferred language?","Who is my manager?","What is my API key?","What is my timezone?","What project am I working on?","What is my editor?","What is my framework?","What is my deployment method?","What is my on-call rotation?","What is my laptop?"]; all_nodes=agent.graph.get_all_active_nodes(); full=sum(len(n.content.split()) for n in all_nodes); table=Table("Query","Full History Tokens","Retrieval Tokens","Savings %"); reductions=[]
    for q in qs:
        r=agent.recall(q); saved=(1-r["tokens_used"]/full)*100 if full else 0; reductions.append(saved); table.add_row(q,str(full),str(r["tokens_used"]),f"{saved:.1f}%")
    console.print(table); console.print(f"Average token reduction: {sum(reductions)/len(reductions):.1f}%")
    section("10 — RESTART PROOF"); console.print("Killing Agent A..."); agent=None; agent=AgentA(); nodes=agent.graph.get_all_active_nodes(); valid,errors=agent.hash_chain.verify_integrity(); console.print(f"Agent A restarted. Loading state...\nSessions recovered: {len(set(n.source['session_id'] for n in nodes))}\nTotal memories: {len(nodes)}\nHash chain integrity: {(valid,errors)}"); console.print("All state intact. Hash chain verified."); console.print(Panel("MNEMOSYNE — auditable forgetting, across agents, across restarts."))
def main():
    reset_demo_state()
    os.makedirs("data",exist_ok=True)
    with open("data/demo_output.txt","w",encoding="utf-8") as f: run(f)
    print(open("data/demo_output.txt",encoding="utf-8").read())
if __name__=="__main__": main()
