"""Reliable end-to-end deletion benchmark.

Success means no active copy remains after deletion and a simulated restart in
the graph, vector store, or filesystem memory. Historical audit metadata is
expected to remain.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode
from stores.filesystem_memory import FilesystemMemory
from stores.vector_store import VectorStore


def make(content, session, source_type):
    return MemoryNode(content=content, source={"type": source_type, "session_id": session, "turn_index": 0}, session_id=session)


def run(count):
    successes, failures = 0, []
    with tempfile.TemporaryDirectory(prefix="mnemosyne_deletion_e2e_") as root:
        root = Path(root)
        graph_path, vector_path = root / "knowledge_graph.json", root / "vectors"
        fs = FilesystemMemory(str(root / "viking_memory"))
        graph = KnowledgeGraph(str(graph_path))
        vectors = VectorStore(collection_name="e2e", persist_directory=str(vector_path))
        audit = HashChain(str(root / "audit_chain.json"))
        erasure = ErasureEngine(str(root / "blocked_inference.json"))
        cases = []
        for index in range(count):
            session = f"customer_{index:05d}"
            target = make(f"Customer {index:05d} email customer-{index:05d}@example.test account-{index:05d}", session, "account_profile")
            child = make(f"Derived support summary for customer {index:05d} account-{index:05d}", session, "derived_summary")
            unrelated = make(f"Independent customer {index:05d}-other account-{index:05d}-other", f"other_{index:05d}", "unrelated_profile")
            for node in (target, child, unrelated):
                graph.add_node(node); vectors.add(node); fs.write_entity(node)
            graph.add_edge(target.node_id, child.node_id, "DERIVED_FROM")
            cases.append((target, child, unrelated))

        for target, child, unrelated in cases:
            report = erasure.delete(target.node_id, vectors, graph, audit, reason="customer requested account erasure", deleted_by="privacy-service")
            restarted_graph = KnowledgeGraph(str(graph_path))
            restarted_vectors = VectorStore(collection_name="e2e", persist_directory=str(vector_path))
            target_after, child_after = restarted_graph.get_node(target.node_id), restarted_graph.get_node(child.node_id)
            unrelated_after = restarted_graph.get_node(unrelated.node_id)
            target_fs, child_fs = fs.read_entity(target.node_id), fs.read_entity(child.node_id)
            checks = {
                "report_has_audit_metadata": bool(report.deleted_by and report.reason and report.timestamp and report.signature),
                "target_non_active_after_restart": bool(target_after and target_after.deletion_state != "active"),
                "child_non_active_after_restart": bool(child_after and child_after.deletion_state != "active"),
                "target_absent_from_vectors": restarted_vectors.get_by_id(target.node_id) is None,
                "child_absent_from_vectors": restarted_vectors.get_by_id(child.node_id) is None,
                "target_filesystem_redacted": not bool(target_fs and target_fs.get("content")),
                "child_filesystem_redacted": not bool(child_fs and child_fs.get("content")),
                "unrelated_data_preserved": bool(unrelated_after and unrelated_after.deletion_state == "active" and restarted_vectors.get_by_id(unrelated.node_id)),
                "inference_blocked": target.node_id in erasure.blocked_ids,
            }
            if all(checks.values()): successes += 1
            elif len(failures) < 10: failures.append({"entity_id": target.node_id, "verdict": report.verdict, "checks": checks})
    rate = successes / count * 100 if count else 0.0
    return {"requests": count, "successful_end_to_end_deletions": successes, "failed_end_to_end_deletions": count - successes, "end_to_end_completion_rate_percent": round(rate, 4), "comparison_baseline_percent": 1.5, "beats_1_5_percent_baseline": rate > 1.5, "success_definition": "No active target/derived copy after restart in graph, vectors, or filesystem; audit retained; unrelated data preserved.", "failures": failures}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    if args.count < 1: parser.error("--count must be positive")
    print(json.dumps(run(args.count), indent=2))
