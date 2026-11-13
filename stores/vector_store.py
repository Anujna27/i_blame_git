import json
from pathlib import Path
from typing import Optional, Union
import warnings

import faiss
import numpy as np

from core.contradiction import ContradictionEngine, embed_text
from core.memory_node import MemoryNode

_TRUST_PRIORITY_BOOST = {
    "verified": 0.20,
    "user_asserted": 0.05,
    "derived": 0.03,
    "contradicted": 0.00,
    "planted": -0.10,
}


def _normalize_vector(vec: Union[list[float], np.ndarray]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm > 0.0:
        arr = arr / norm
    return arr


class VectorStore:
    """FAISS-backed persistent vector store with soft-delete and trust-aware recall."""

    def __init__(
        self,
        collection_name: str = "memory",
        persist_directory: str = "data/faiss_db",
        dim: int = 384,
        enable_conflict_detection: bool = True,
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.dim = dim
        self._dir = Path(persist_directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / f"{collection_name}.faiss"
        self._meta_path = self._dir / f"{collection_name}_meta.json"

        self._records: dict[str, dict] = {}
        self._id_order: list[str] = []
        self.index = faiss.IndexFlatIP(self.dim)
        self.last_warnings: list[str] = []
        # Unlearning and other high-volume retrieval benchmarks do not need
        # contradiction expansion on every query.  Keep it enabled by default
        # for normal application use, but allow callers to opt out explicitly.
        self.enable_conflict_detection = enable_conflict_detection
        self._contradiction_engine = ContradictionEngine()

        self._load()

    def _rebuild_index(self) -> None:
        self.index = faiss.IndexFlatIP(self.dim)
        if not self._id_order:
            return
        matrix = np.vstack(
            [_normalize_vector(self._records[nid]["embedding"]) for nid in self._id_order]
        ).astype(np.float32)
        self.index.add(matrix)

    def _persist(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "dim": self.dim,
            "id_order": self._id_order,
            "records": self._records,
        }
        self._meta_path.write_text(json.dumps(payload), encoding="utf-8")
        faiss.write_index(self.index, str(self._index_path))

    def _load(self) -> None:
        if not self._meta_path.exists():
            return
        payload = json.loads(self._meta_path.read_text(encoding="utf-8"))
        self.dim = int(payload.get("dim", self.dim))
        self._records = payload.get("records", {})
        self._id_order = payload.get("id_order", list(self._records.keys()))
        if self._index_path.exists():
            self.index = faiss.read_index(str(self._index_path))
            if self.index.ntotal != len(self._id_order):
                self._rebuild_index()
        else:
            self._rebuild_index()

    def add(
        self,
        node: MemoryNode,
        embedding: Optional[list[float]] = None,
        persist: bool = True,
    ) -> None:
        """Add or update a MemoryNode in the vector store, generating an embedding if omitted."""
        raw_vec = embedding if embedding is not None else embed_text(node.content)
        vec = _normalize_vector(raw_vec)

        if not self._records and int(vec.shape[0]) != self.dim:
            self.dim = int(vec.shape[0])
            self.index = faiss.IndexFlatIP(self.dim)

        is_update = node.node_id in self._records
        self._records[node.node_id] = {
            "active": node.deletion_state == "active",
            "trust_status": node.trust_status,
            "node_json": node.to_jsonld(),
            "embedding": vec.tolist(),
        }
        if is_update:
            self._rebuild_index()
        else:
            self._id_order.append(node.node_id)
            self.index.add(vec.reshape(1, -1))
        if persist:
            self._persist()

    def persist(self) -> None:
        """Flush the current FAISS index and metadata to disk."""
        self._persist()

    def remove(self, node_id: str) -> None:
        """Hard-delete a node from the vector index and metadata."""
        if node_id not in self._records:
            return
        del self._records[node_id]
        self._id_order = [nid for nid in self._id_order if nid != node_id]
        self._rebuild_index()
        self._persist()

    def remove_many(self, node_ids: list[str] | set[str] | tuple[str, ...]) -> None:
        """Hard-delete several nodes with one index rebuild and one disk write."""
        ids = {str(node_id) for node_id in node_ids}
        existing = ids.intersection(self._records)
        if not existing:
            return
        for node_id in existing:
            del self._records[node_id]
        self._id_order = [node_id for node_id in self._id_order if node_id not in existing]
        self._rebuild_index()
        self._persist()

    def remove_from_active_index(self, node_id: str) -> None:
        """Soft-delete a node by setting metadata active=False without removing its document."""
        if node_id not in self._records:
            return
        self._records[node_id]["active"] = False
        self._persist()

    def export_snapshot(self) -> dict:
        """Export rebuildable FAISS metadata and embeddings for capsule portability."""
        return {"dim": self.dim, "id_order": list(self._id_order), "records": self._records}

    def import_snapshot(self, snapshot: dict) -> None:
        self.dim = int(snapshot.get("dim", self.dim))
        self._id_order = list(snapshot.get("id_order", []))
        self._records = dict(snapshot.get("records", {}))
        self._rebuild_index()
        self._persist()

    def get_by_id(self, node_id: str) -> Optional[MemoryNode]:
        """Fetch a MemoryNode by its ID, or return None if absent."""
        rec = self._records.get(node_id)
        if not rec:
            return None
        return MemoryNode.from_jsonld(rec["node_json"])

    def _get_all_active_nodes(self) -> dict[str, MemoryNode]:
        nodes: dict[str, MemoryNode] = {}
        for nid, rec in self._records.items():
            if rec.get("active", True):
                nodes[nid] = MemoryNode.from_jsonld(rec["node_json"])
        return nodes

    def query(
        self,
        query_text_or_embedding: Union[str, list[float]],
        top_k: int = 5,
        include_conflict_warnings: Optional[bool] = None,
    ) -> list[MemoryNode]:
        """Query active documents, prioritizing verified nodes and surfacing user-asserted conflicts."""
        self.last_warnings = []
        if top_k <= 0 or self.index.ntotal == 0:
            return []

        active_map = self._get_all_active_nodes()
        if not active_map:
            return []

        raw_query = (
            embed_text(query_text_or_embedding)
            if isinstance(query_text_or_embedding, str)
            else query_text_or_embedding
        )
        query_vec = _normalize_vector(raw_query).reshape(1, -1)

        scores, indices = self.index.search(query_vec, self.index.ntotal)

        scored: list[tuple[float, MemoryNode]] = []
        for idx, sim_score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self._id_order):
                continue
            nid = self._id_order[idx]
            node = active_map.get(nid)
            if node is None:
                continue
            sim = max(0.0, float(sim_score))
            boost = _TRUST_PRIORITY_BOOST.get(node.trust_status, 0.0)
            scored.append((sim + boost, node))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected: list[MemoryNode] = [node for _, node in scored[:top_k]]
        selected_ids = {node.node_id for node in selected}

        if include_conflict_warnings is None:
            include_conflict_warnings = self.enable_conflict_detection
        if not include_conflict_warnings:
            return selected

        # CRITICAL RULE: Never silently pick one when two user_asserted (or contradicted) nodes conflict.
        active_list = list(active_map.values())
        extra_nodes: list[MemoryNode] = []
        warned_pairs: set[tuple[str, str]] = set()

        for node in selected:
            if node.trust_status not in ("user_asserted", "contradicted"):
                continue

            partner_ids = list(node.contradicts) + [
                conflict.node_b_id
                for conflict in self._contradiction_engine.detect(node, active_list)
            ]
            for partner_id in partner_ids:
                partner = active_map.get(partner_id)
                if not partner or partner.trust_status not in ("user_asserted", "contradicted"):
                    continue
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
