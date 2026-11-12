# Core Engine — Integration Guide (M1)

## Quick start

from core.memory_node import MemoryNode
from core.hash_chain import HashChain
from core.knowledge_graph import KnowledgeGraph
from core.erasure_engine import ErasureEngine
from core.residual_risk import ResidualRiskReporter

## MemoryNode and KnowledgeGraph

Fields: node_id, content, source, trust_status, derivation_edges, version, supersedes, contradicts, deletion_state, is_blocked, created_at, last_accessed, access_count

trust_status must be one of: verified, user_asserted, derived, contradicted, planted
deletion_state must be one of: active, source_removed, invalidated

## Minimal example

node = MemoryNode(
    content="User's API key is sk-abc123",
    source={"type": "conversation_turn", "session_id": "s1",
            "turn_index": 17, "timestamp": "2026-11-12T14:32:00Z",
            "raw_reference": "s1_t17"},
    trust_status="user_asserted",
)

## Erasure engine contract

ErasureEngine().delete(node_id, vector_store, graph_store, hash_chain) -> ErasureReport

The engine calls these methods on your stores:

vector_store.remove_from_active_index(node_id) -> None
vector_store.query(query_text, top_k=3) -> list[MemoryNode]
knowledge_graph.get_node(node_id) -> Optional[MemoryNode]
graph_store.get_descendants(node_id) -> list[str]
graph_store.get_all_active_nodes() -> list[MemoryNode]

If your method names differ, message M1 in #contracts. M1 will add an adapter — do not rewrite your store.

## Displaying the notice

report = ErasureEngine().delete(node_id, vec, graph, hc)
notice = ResidualRiskReporter().generate_notice(report)
print(notice)  # ASCII box, safe for st.code(notice, language=None)

## Hash chain

hash_chain.append("operation_name", node_id, {"any": "details"})
ok, errors = hash_chain.verify_integrity()

## ErasureReport shape

report.node_id: str
report.node_content: str
report.levels: list of 5 LevelResult (level_number, level_name, status, details, evidence)
report.verdict: "fully_deleted" | "partially_deleted" | "failed"
report.residual_risks: list of ResidualRisk (risk_type, cluster, description, severity, affected_node_ids)
report.timestamp: ISO string
report.signature: SHA256 hex string

## Level 5 is expected to fail

When descendants exist, Level 5 will report "failed" with the details "LLM consolidation is non-deterministic...". This is CORRECT and HONEST. Do not try to force a pass. The whole point of the project is honest reporting of residual risk.

## Questions

Ping M1 in #blockers. M1 is on support duty for 90 minutes after Sync 1.
