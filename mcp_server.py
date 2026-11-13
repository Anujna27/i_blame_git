"""
mcp_server.py

Model Context Protocol (MCP) server exposing Mnemosyne memory tools to external AI agents.
Uses the official mcp Python SDK (FastMCP) to expose memory operations:
- remember: Store memory with provenance and contradiction detection
- recall: Retrieve bounded, deletion-safe context (or abstain with "I don't know.")
- forget: Execute 5-level cryptographic erasure and return the accountability report
"""

import os
import shutil

# Isolate MCP server database to avoid benchmark pollution
if os.path.exists("data/mcp_live_demo"):
    shutil.rmtree("data/mcp_live_demo")
os.makedirs("data/mcp_live_demo", exist_ok=True)

from dataclasses import asdict
import json
from typing import Optional

from mcp.server.fastmcp import FastMCP
from agents.agent_a import AgentA
from agents.blocked_loader import load_blocked_ids
from core.memory_node import MemoryNode

# Ensure MemoryNode supports .get() method for dict-like access
if not hasattr(MemoryNode, "get"):
    MemoryNode.get = lambda self, k, default=None: getattr(self, k, default)

# 2. Initialize the server
mcp = FastMCP("mnemosyne-memory")

# 3. Instantiate AgentA with isolated data directory
try:
    from eval.llm_backends import MockBackend
    agent = AgentA(data_dir="data/mcp_live_demo/", backend=MockBackend())
except Exception:
    agent = AgentA(data_dir="data/mcp_live_demo/")

# Ensure erasure_engine is accessible from the agent object
if not hasattr(agent, "erasure_engine"):
    agent.erasure_engine = getattr(agent, "erasure", None)


# 4. Define three tools using the @mcp.tool() decorator

@mcp.tool()
def remember(content: str, trust_status: str = "user_asserted") -> str:
    """
    Store a memory into Mnemosyne's memory layer with provenance and contradiction detection.

    Args:
        content: The text content of the memory to store.
        trust_status: Trust status of the memory (e.g. 'user_asserted', 'derived').

    Returns:
        Confirmation string containing the newly created node ID.
    """
    node = agent.remember(content, source={"type": "mcp_call"}, trust_status=trust_status)
    return f"Memory stored with ID: {node.node_id}"


@mcp.tool()
def recall(query: str, token_budget: int = 2000) -> str:
    """Retrieve context from Mnemosyne memory, filtering out low-relevance noise."""
    # Assuming agent.recall returns a dictionary with 'answer' and 'sources'
    # If agent.recall is a black box, we need to intercept the vector search directly.

    # Better approach: If AgentA has a vector_store, query it directly with a threshold
    if hasattr(agent, "vector_store"):
        raw_results = agent.vector_store.query(query, top_k=5)

        # Attach similarity score if not already present on nodes
        if raw_results:
            try:
                from core.contradiction import embed_text
                import numpy as np

                q_vec = np.asarray(embed_text(query), dtype=np.float32)
                q_norm = float(np.linalg.norm(q_vec))
                if q_norm > 0:
                    q_vec = q_vec / q_norm
                for n in raw_results:
                    if getattr(n, "score", None) is None:
                        c = n.get("content", "") if isinstance(n, dict) else getattr(n, "content", "")
                        c_vec = np.asarray(embed_text(c), dtype=np.float32)
                        c_norm = float(np.linalg.norm(c_vec))
                        sim = float(np.dot(q_vec, c_vec / c_norm)) if (c_norm > 0 and q_norm > 0) else 0.0
                        if isinstance(n, dict):
                            n["score"] = sim
                        else:
                            setattr(n, "score", sim)
            except Exception:
                pass

        filtered_context = []
        for node in raw_results:
            # Check for similarity score (handle both dict and object attributes)
            score = node.get("score", 0) if isinstance(node, dict) else getattr(node, "score", 0)

            # STRICT THRESHOLD: Only include if similarity is > 0.4 (40% match)
            if score and score > 0.4:
                content = node.get("content") if isinstance(node, dict) else node.content
                filtered_context.append(content)

        if not filtered_context:
            return "I don't know."

        return "\n".join(filtered_context)

    # Fallback if vector_store isn't exposed directly
    result = agent.recall(query, token_budget)
    if result.get("abstained", False):
        return "I don't know."
    return result.get("answer", "I don't know.")


@mcp.tool()
def forget(
    target: str = "",
    reason: str = "user_requested_erasure",
    actor: str = "user",
    node_id: Optional[str] = None,
    topic: Optional[str] = None,
) -> str:
    """
    Deletes memories from Mnemosyne using a unified erasure interface.
    Accepts either a specific memory ID (UUID) or a topic/keyword (Viking 3-Tier semantic search).

    Args:
        target: The topic keyword (e.g. 'calisthenics', 'Python') or exact memory node ID to erase.
        reason: Justification for erasure (e.g., GDPR, user correction).
        actor: Identity of actor requesting erasure.
        node_id: Optional explicit memory node ID override.
        topic: Optional explicit topic override.

    Returns:
        Erasure report JSON for specific ID deletions, or summary message for topic-based deletions.
    """
    identifier = (node_id or topic or target or "").strip()
    if not identifier:
        return "Please provide a memory ID or topic to forget."

    # Check if identifier corresponds to a specific node ID (explicit node_id, exists in memory, or UUID)
    is_specific_node = False
    if node_id:
        is_specific_node = True
    elif identifier in agent.all_nodes or (hasattr(agent, "graph") and agent.graph.has_entity(identifier)):
        is_specific_node = True
    else:
        try:
            import uuid

            uuid.UUID(identifier)
            is_specific_node = True
        except (ValueError, AttributeError):
            is_specific_node = False

    if is_specific_node:
        # Single-node 5-level cryptographic erasure
        report = agent.forget(identifier, reason=reason, actor=actor)
        if hasattr(report, "__dataclass_fields__"):
            report_data = asdict(report)
        elif hasattr(report, "to_dict"):
            report_data = report.to_dict()
        elif isinstance(report, dict):
            report_data = report
        else:
            report_data = {
                "verdict": getattr(report, "verdict", "unknown"),
                "residual_risks": getattr(report, "residual_risks", []),
                "node_id": identifier,
            }
        try:
            from core.residual_risk import ResidualRiskReporter

            report_data["accountability_notice"] = ResidualRiskReporter().generate_notice(report)
        except Exception:
            pass
        return json.dumps(report_data, indent=2, default=str)

    # Viking 3-Tier Topic Erasure
    results = agent.vector_store.query(identifier, top_k=50)
    if not results:
        return json.dumps(
            {
                "summary": f"No memories found related to '{identifier}'.",
                "verdict": "not_found",
                "levels": [],
                "residual_risks": [],
            },
            indent=2,
        )

    deleted_count = 0
    skipped_count = 0
    reports = []

    for node in results:
        nid = node.get("node_id") if isinstance(node, dict) else node.node_id
        l2_content = node.get("content_l2") or node.get("content") or ""
        if isinstance(node, dict) and not l2_content:
            l2_content = node.get("content", "")

        # Strict keyword filter on L2 Content (prevents collateral deletion)
        if identifier.lower() not in l2_content.lower():
            skipped_count += 1
            continue

        try:
            report = agent.erasure_engine.delete(
                nid,
                agent.vector_store,
                agent.graph,
                agent.hash_chain,
                reason=reason,
                deleted_by=actor,
            )
            reports.append(report)
            deleted_count += 1
        except Exception:
            pass

    # Refresh agent blocked IDs and node caches if deletions occurred
    if deleted_count > 0:
        blocked_path = (
            os.path.join(agent.data_dir, "blocked_inference.json")
            if getattr(agent, "data_dir", None)
            else "data/blocked_inference.json"
        )
        agent.blocked_ids = load_blocked_ids(path=blocked_path)
        for nid in list(agent.all_nodes):
            refreshed = agent.graph.get_node(nid)
            if refreshed is not None:
                agent.all_nodes[nid] = refreshed

    if deleted_count == 0:
        return json.dumps(
            {
                "summary": f"Found {len(results)} related memories, but none explicitly contained the word '{identifier}' in their L2 content. Nothing deleted. (Skipped {skipped_count} collateral memories).",
                "verdict": "none_deleted",
                "levels": [],
                "residual_risks": [],
            },
            indent=2,
        )

    # Build the 5-layer accountability report
    primary_report = reports[-1]
    if hasattr(primary_report, "__dataclass_fields__"):
        report_data = asdict(primary_report)
    elif hasattr(primary_report, "to_dict"):
        report_data = primary_report.to_dict()
    else:
        report_data = {
            "verdict": getattr(primary_report, "verdict", "fully_deleted"),
            "residual_risks": getattr(primary_report, "residual_risks", []),
            "node_id": getattr(primary_report, "node_id", ""),
        }

    report_data["summary"] = (
        f"Successfully deleted {deleted_count} memories explicitly containing '{identifier}'. (Skipped {skipped_count} collateral memories)."
    )

    try:
        from core.residual_risk import ResidualRiskReporter

        report_data["accountability_notice"] = ResidualRiskReporter().generate_notice(primary_report)
    except Exception:
        pass

    if len(reports) > 1:
        report_data["total_deleted"] = deleted_count
        report_data["all_reports"] = [
            asdict(r) if hasattr(r, "__dataclass_fields__") else (r.to_dict() if hasattr(r, "to_dict") else str(r))
            for r in reports
        ]

    return json.dumps(report_data, indent=2, default=str)


def forget_topic(topic: str, reason: str = "user_requested_erasure", actor: str = "user") -> str:
    """Helper alias for topic-based erasure (backward compatible in code without creating a duplicate MCP button)."""
    return forget(target=topic, reason=reason, actor=actor, topic=topic)


# 5. Standard MCP entry point
if __name__ == "__main__":
    mcp.run(transport="stdio")

