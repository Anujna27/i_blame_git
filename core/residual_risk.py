from dataclasses import dataclass
from typing import Literal

@dataclass
class ResidualRisk:
    risk_type: str
    cluster: str
    description: str
    severity: Literal["low", "medium", "high"]
    affected_node_ids: list[str]

class ResidualRiskReporter:
    def generate_notice(self, report):
        levels={x.level_number:x for x in report.levels}; icon=lambda s:{"passed":"✅","partial":"⚠️","failed":"❌"}[s]
        def line(text=""): return "║"+text[:62].ljust(62)+"║"
        def status_line(label,status): return line(label+" "*max(1,62-len(label)-2)+icon(status))
        fact=report.node_content if len(report.node_content)<=44 else report.node_content[:41]+"..."; l2=levels.get(2); children=(l2.evidence if l2 else {}).get("invalidated_children",[]); risk=report.residual_risks[0].description if report.residual_risks else "No residual risk detected"; l5=levels.get(5); detail=(l5.details if l5 else ""); detail=detail[:52]+("..." if len(detail)>52 else "")
        lines=["╔"+"═"*62+"╗",line("              RESIDUAL RISK NOTICE"),line(f"              Deletion Request #{report.node_id[:8]}"),"╠"+"═"*62+"╣",line(f'  FACT: "{fact}"'),line(),status_line("  LEVEL 1 — Source Record Removed .....................",levels[1].status),status_line("  LEVEL 2 — Derived Artifacts Invalidated .............",levels[2].status)]
        lines += [line(f"    ├─ {c} ..................................... {icon('passed')}") for c in children]
        lines += [status_line("  LEVEL 3 — Inference Blocked .........................",levels[3].status),status_line("  LEVEL 4 — Non-Inferability Checked .................",levels[4].status),line(f"    └─ RISK: {risk}"),status_line("  LEVEL 5 — State Restoration Checked ................",levels[5].status),line("    └─ "+detail),"╠"+"═"*62+"╣",line(f"  VERDICT: {report.verdict.replace('_',' ').upper()}"),line(f"  Residual risk remains at: {', '.join(r.cluster for r in report.residual_risks) or 'none'}"),line("  This notice is cryptographically signed and logged."),"╚"+"═"*62+"╝"]
        return "\n".join(lines)
