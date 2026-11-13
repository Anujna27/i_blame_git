"""Simulate a real customer account-erasure request in isolated storage."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode
from stores.vector_store import VectorStore


def make(content, session, source_type):
    return MemoryNode(
        content=content,
        source={"type": source_type, "session_id": session, "turn_index": 0},
        session_id=session,
    )


with tempfile.TemporaryDirectory(prefix="mnemosyne_real_life_") as root:
    root = Path(root)
    graph = KnowledgeGraph(str(root / "knowledge_graph.json"))
    vectors = VectorStore(collection_name="real_life", persist_directory=str(root / "vectors"))
    audit = HashChain(str(root / "audit_chain.json"))
    erasure = ErasureEngine(str(root / "blocked_inference.json"))

    # Customer account to be erased.
    profile = make(
        "Customer Priya Nair, email priya.nair@example.com, account 48291.",
        "customer_priya",
        "account_profile",
    )
    preference = make(
        "Priya prefers email support and vegetarian meal recommendations.",
        "customer_priya",
        "preference",
    )
    purchase = make(
        "Priya purchased an annual support plan on 2026-02-14.",
        "customer_priya",
        "purchase_history",
    )
    summary = make(
        "Support summary derived from Priya's profile and purchase history: high-value annual customer.",
        "customer_priya",
        "derived_support_summary",
    )

    # Similar-looking but independent customer data must remain.
    other_customer = make(
        "Customer Priyanka Nair, email priyanka.nair@example.com, account 77104.",
        "customer_priyanka",
        "account_profile",
    )

    all_nodes = [profile, preference, purchase, summary, other_customer]
    for node in all_nodes:
        vectors.add(node)
        graph.add_node(node)

    graph.add_edge(profile.node_id, preference.node_id, "RELATED_TO")
    graph.add_edge(profile.node_id, purchase.node_id, "OWNS")
    graph.add_edge(profile.node_id, summary.node_id, "DERIVED_FROM")

    print("ACCOUNT ERASURE REQUEST")
    print("customer: Priya Nair")
    print("entities before:", len(graph.get_all_active_nodes()))
    print("profile id:", profile.node_id)
    print("derived summary id:", summary.node_id)

    report = erasure.delete(
        profile.node_id,
        vectors,
        graph,
        audit,
        reason="customer requested account erasure",
        deleted_by="privacy-service",
    )

    print("\nERASURE REPORT")
    print(json.dumps(report.to_dict(), indent=2, default=str))

    print("\nPOST-ERASURE INVENTORY")
    for node in all_nodes:
        current = graph.get_node(node.node_id)
        print(json.dumps({
            "type": node.entity_type,
            "id": node.node_id,
            "state": current.deletion_state if current else "missing",
            "vector_present": vectors.get_by_id(node.node_id) is not None,
            "content_present": bool(current and current.content),
        }))

    remaining_active = [n.node_id for n in graph.get_all_active_nodes()]
    print("\nEXPECTED INTERPRETATION")
    print("Priya profile and derived records should not be active or vector-retrievable.")
    print("Priyanka's independent account should remain active.")
    print("Strict verdict may be partially_deleted because derived history and semantic neighbors create residual risk.")
    print("active entity count after:", len(remaining_active))
