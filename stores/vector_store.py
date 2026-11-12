import json
from typing import Optional, Union
import warnings

import chromadb

from core.contradiction import ContradictionEngine, embed_text
from core.memory_node import MemoryNode

_TRUST_PRIORITY_BOOST = {
    "verified": 0.20,
    "user_asserted": 0.05,
    "derived": 0.03,
    "contradicted": 0.00,
    "planted": -0.10,
}


class VectorStore:
    """ChromaDB-backed persistent vector store with soft-delete and trust-aware recall."""

    def __init__(self, collection_name: str = "memory", persist_directory: str = "data/chroma_db"):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.last_warnings: list[str] = []
        self._contradiction_engine = ContradictionEngine()

    def add(self, node: MemoryNode, embedding: Optional[list[float]] = None) -> None:
        """Add or update a MemoryNode in the vector store, generating an embedding if omitted."""
        vec = embedding if embedding is not None else embed_text(node.content)
        metadata = {
            "active": node.deletion_state == "active",
            "trust_status": node.trust_status,
            "node_json": json.dumps(node.to_jsonld()),
        }
        self.collection.upsert(
            ids=[node.node_id],
            documents=[node.content],
            embeddings=[vec],
            metadatas=[metadata],
        )

    def remove(self, node_id: str) -> None:
        """Hard-delete a node from the vector collection."""
        self.collection.delete(ids=[node_id])

    def remove_from_active_index(self, node_id: str) -> None:
        """Soft-delete a node by setting metadata active=False without removing its document."""
        existing = self.collection.get(ids=[node_id], include=["metadatas"])
        if not existing["ids"]:
            return
        meta = dict(existing["metadatas"][0] or {})
        meta["active"] = False
        self.collection.update(ids=[node_id], metadatas=[meta])

    def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        """Fetch a MemoryNode by its ID, or return None if absent."""
        res = self.collection.get(ids=[node_id], include=["metadatas"])
        if not res["ids"]:
            return None
        meta = res["metadatas"][0]
        return MemoryNode.from_jsonld(json.loads(meta["node_json"]))

    def _get_all_active_nodes(self) -> dict[str, MemoryNode]:
        res = self.collection.get(where={"active": True}, include=["metadatas"])
        nodes: dict[str, MemoryNode] = {}
        for meta in res.get("metadatas") or []:
            node = MemoryNode.from_jsonld(json.loads(meta["node_json"]))
            nodes[node.node_id] = node
        return nodes

    def query(
        self,
        query_text_or_embedding: Union[str, list[float]],
        top_k: int = 5,
    ) -> list[MemoryNode]:
        """Query active documents, prioritizing verified nodes and surfacing user-asserted conflicts."""
        self.last_warnings = []
        if top_k <= 0:
            return []

        active_map = self._get_all_active_nodes()
        if not active_map:
            return []

        query_vec = (
            embed_text(query_text_or_embedding)
            if isinstance(query_text_or_embedding, str)
            else list(query_text_or_embedding)
        )

        n_results = min(len(active_map), max(top_k * 3, 10))
        res = self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results,
            where={"active": True},
            include=["metadatas", "distances"],
        )

        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]

        scored: list[tuple[float, MemoryNode]] = []
        for meta, dist in zip(metadatas, distances):
            node = MemoryNode.from_jsonld(json.loads(meta["node_json"]))
            sim = max(0.0, 1.0 - float(dist))
            boost = _TRUST_PRIORITY_BOOST.get(node.trust_status, 0.0)
            scored.append((sim + boost, node))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected: list[MemoryNode] = [node for _, node in scored[:top_k]]
        selected_ids = {node.node_id for node in selected}

        # CRITICAL RULE: Never silently pick one when two user_asserted (or contradicted) nodes conflict.
        active_list = list(active_map.values())
        extra_nodes: list[MemoryNode] = []
        warned_pairs: set[tuple[str, str]] = set()

        for node in selected:
            if node.trust_status not in ("user_asserted", "contradicted"):
                continue

            for partner_id in node.contradicts:
                partner = active_map.get(partner_id)
                if partner and partner.trust_status in ("user_asserted", "contradicted"):
                    pair = tuple(sorted((node.node_id, partner.node_id)))
                    if pair not in warned_pairs:
                        warned_pairs.add(pair)
                        msg = (
                            f"Warning: Contradicting user-asserted memories detected "
                            f"({pair[0]} vs {pair[1]}). Returning both."
                        )
                        self.last_warnings.append(msg)
                        warnings.warn(msg, UserWarning, stacklevel=2)
                    if partner.node_id not in selected_ids:
                        selected_ids.add(partner.node_id)
                        extra_nodes.append(partner)

            detected = self._contradiction_engine.detect(node, active_list)
            for conflict in detected:
                partner = active_map.get(conflict.node_b_id)
                if partner and partner.trust_status in ("user_asserted", "contradicted"):
                    pair = tuple(sorted((node.node_id, partner.node_id)))
                    if pair not in warned_pairs:
                        warned_pairs.add(pair)
                        msg = (
                            f"Warning: Contradicting user-asserted memories detected "
                            f"({pair[0]} vs {pair[1]}). Returning both."
                        )
                        self.last_warnings.append(msg)
                        warnings.warn(msg, UserWarning, stacklevel=2)
                    if partner.node_id not in selected_ids:
                        selected_ids.add(partner.node_id)
                        extra_nodes.append(partner)

        return selected + extra_nodes

