from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional, Union

import networkx as nx

ALLOWED_RELATIONSHIPS = {
    "PREFERS",
    "OWNS",
    "EXTRACTED_FROM",
    "DERIVED_FROM",
    "CONTRADICTS",
    "RELATED_TO",
    "SESSION_MEMBER",
    "MENTIONS",
}


class KnowledgeGraph:
    """NetworkX DiGraph-backed Knowledge Graph for entity memory and relationships."""

    def __init__(self, path: str = "data/knowledge_graph.json"):
        self.path = str(path) if path else ""
        self.graph = nx.DiGraph()
        if self.path and Path(self.path).exists():
            self.load()

    def _normalize_entity(self, node: Any) -> dict:
        if hasattr(node, "to_jsonld") and callable(node.to_jsonld):
            data = node.to_jsonld()
        elif hasattr(node, "model_dump") and callable(node.model_dump):
            try:
                data = node.model_dump(mode="json")
            except Exception:
                data = node.model_dump()
        elif hasattr(node, "dict") and callable(node.dict):
            data = node.dict()
        elif isinstance(node, dict):
            data = dict(node)
        else:
            data = dict(getattr(node, "__dict__", {}))

        node_id = data.get("node_id")
        if not node_id:
            raise ValueError("node_id is required")
        node_id = str(node_id)

        session_id = data.get("session_id")
        if not session_id:
            src = data.get("source")
            if isinstance(src, dict):
                session_id = src.get("session_id", "")
            elif hasattr(src, "session_id"):
                session_id = getattr(src, "session_id", "")
        session_id = str(session_id or "")

        entity_type = str(data.get("entity_type") or "unknown")
        content = str(data.get("content") or "")
        deletion_state = str(data.get("deletion_state") or "active")
        version = int(data.get("version", 1))
        lifecycle = list(data.get("lifecycle") or [])
        properties = dict(data.get("properties") or {})

        canonical = {
            "node_id": node_id,
            "entity_type": entity_type,
            "content": content,
            "session_id": session_id,
            "deletion_state": deletion_state,
            "version": version,
            "lifecycle": lifecycle,
            "properties": properties,
        }

        # Store any remaining non-canonical keys inside properties if not already present
        for k, v in data.items():
            if k not in canonical and k not in canonical["properties"]:
                canonical["properties"][k] = v

        return canonical

    def add_entity(self, node: Any) -> dict:
        """Accepts MemoryNode or dict. Normalizes to canonical dict.

        If node_id already exists, updates content/metadata but keeps history.
        Returns the stored dict.
        """
        canonical = self._normalize_entity(node)
        node_id = canonical["node_id"]

        if self.graph.has_node(node_id):
            existing = dict(self.graph.nodes[node_id])
            history = list(existing.get("lifecycle") or [])
            update_entry = {
                "action": "update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "previous_version": existing.get("version", 1),
                "previous_content": existing.get("content", ""),
            }
            history.append(update_entry)
            if canonical.get("lifecycle"):
                history.extend(canonical["lifecycle"])
            canonical["lifecycle"] = history

            prev_ver = existing.get("version", 1)
            if canonical["version"] <= prev_ver:
                canonical["version"] = prev_ver + 1

            merged_props = dict(existing.get("properties") or {})
            merged_props.update(canonical.get("properties") or {})
            canonical["properties"] = merged_props

        self.graph.add_node(node_id, **canonical)
        self.persist()
        return dict(self.graph.nodes[node_id])

    def get_entity(self, node_id: str) -> Optional[dict]:
        """Return the canonical dict or None."""
        if not self.graph.has_node(node_id):
            return None
        node_data = dict(self.graph.nodes[node_id])
        node_data["node_id"] = node_id
        return node_data

    def has_entity(self, node_id: str) -> bool:
        """Check whether an entity exists in the graph."""
        return self.graph.has_node(node_id)

    def remove_entity_edges(self, node_id: str) -> int:
        """Remove ALL edges (in and out) incident to node_id. Do NOT remove the node itself. Return count of edges removed."""
        if not self.graph.has_node(node_id):
            return 0

        in_edges = list(self.graph.in_edges(node_id))
        out_edges = list(self.graph.out_edges(node_id))
        all_edges = set(in_edges) | set(out_edges)
        count = len(all_edges)

        for u, v in all_edges:
            if self.graph.has_edge(u, v):
                self.graph.remove_edge(u, v)

        self.persist()
        return count

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Add typed edge. Both endpoints must exist (raise ValueError if not). Relationship must be in ALLOWED_RELATIONSHIPS.

        The edge metadata stored on the graph should include at minimum:
        relationship, created_at (ISO string), created_by (from metadata.get('actor') or 'system'),
        confidence (metadata.get('confidence', 1.0)), source_session (metadata.get('source_session', '')).
        Merge any additional metadata keys. Return the stored edge attributes.
        """
        if not self.graph.has_node(source_id):
            raise ValueError(f"Source entity '{source_id}' does not exist in graph")
        if not self.graph.has_node(target_id):
            raise ValueError(f"Target entity '{target_id}' does not exist in graph")
        if relationship not in ALLOWED_RELATIONSHIPS:
            raise ValueError(
                f"Relationship '{relationship}' not in ALLOWED_RELATIONSHIPS: {sorted(ALLOWED_RELATIONSHIPS)}"
            )

        meta = dict(metadata or {})
        edge_attrs = {
            "relationship": relationship,
            "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "created_by": meta.get("actor") or meta.get("created_by") or "system",
            "confidence": float(meta.get("confidence", 1.0)),
            "source_session": str(meta.get("source_session", "")),
        }

        for k, v in meta.items():
            if k not in edge_attrs:
                edge_attrs[k] = v

        self.graph.add_edge(source_id, target_id, **edge_attrs)
        self.persist()
        return dict(self.graph.edges[source_id, target_id])

    def get_neighbors(
        self,
        node_id: str,
        relationship: Optional[str] = None,
        direction: str = "out",
    ) -> list[dict]:
        """direction is 'out', 'in', or 'both'. If relationship is provided, filter by that edge type. Returns list of neighbor node dicts."""
        if not self.graph.has_node(node_id):
            return []

        if direction not in ("out", "in", "both"):
            raise ValueError(f"Invalid direction '{direction}'. Must be 'out', 'in', or 'both'.")

        neighbor_ids: list[str] = []
        seen: set[str] = set()

        def _add(nid: str):
            if nid not in seen and self.graph.has_node(nid):
                seen.add(nid)
                neighbor_ids.append(nid)

        if direction in ("out", "both"):
            for _, target, data in self.graph.out_edges(node_id, data=True):
                if relationship is None or data.get("relationship") == relationship:
                    _add(target)

        if direction in ("in", "both"):
            for source, _, data in self.graph.in_edges(node_id, data=True):
                if relationship is None or data.get("relationship") == relationship:
                    _add(source)

        results: list[dict] = []
        for nid in neighbor_ids:
            ent = self.get_entity(nid)
            if ent is not None:
                results.append(ent)
        return results

    def get_related_entities(
        self,
        node_id: str,
        max_hops: int = 2,
        relationship: Optional[str] = None,
    ) -> list[dict]:
        """BFS up to max_hops, return unique entities (excluding the start node). If relationship is set, only traverse edges of that type."""
        if not self.graph.has_node(node_id) or max_hops <= 0:
            return []

        visited: set[str] = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        result_entities: list[dict] = []

        while queue:
            curr, hop = queue.popleft()
            if hop >= max_hops:
                continue

            for _, target, data in self.graph.out_edges(curr, data=True):
                if relationship is not None and data.get("relationship") != relationship:
                    continue
                if target not in visited:
                    visited.add(target)
                    ent = self.get_entity(target)
                    if ent is not None:
                        result_entities.append(ent)
                    queue.append((target, hop + 1))

        return result_entities

    def get_all_entities(self, include_deleted: bool = False) -> list[dict]:
        """Return all entity dicts. If include_deleted is False, skip nodes with deletion_state in {source_removed, invalidated}."""
        deleted_states = {"source_removed", "invalidated"}
        entities: list[dict] = []
        for nid in self.graph.nodes:
            ent = self.get_entity(nid)
            if ent is None:
                continue
            if not include_deleted and ent.get("deletion_state") in deleted_states:
                continue
            entities.append(ent)
        return entities

    def get_active_entities(self) -> list[dict]:
        """Return only entities where deletion_state == 'active'."""
        entities: list[dict] = []
        for nid in self.graph.nodes:
            ent = self.get_entity(nid)
            if ent is not None and ent.get("deletion_state") == "active":
                entities.append(ent)
        return entities

    def get_edges(self, include_deleted: bool = False) -> list[dict]:
        """Return list of {source, target, relationship, metadata...} for all edges. If include_deleted is False, skip edges where either endpoint is not active."""
        edges: list[dict] = []
        for u, v, data in self.graph.edges(data=True):
            if not include_deleted:
                u_ent = self.get_entity(u)
                v_ent = self.get_entity(v)
                if not u_ent or u_ent.get("deletion_state") != "active":
                    continue
                if not v_ent or v_ent.get("deletion_state") != "active":
                    continue
            edge_dict = {"source": u, "target": v}
            edge_dict.update(data)
            edges.append(edge_dict)
        return edges

    def persist(self) -> None:
        """Save the graph to self.path using networkx.node_link_data. mkdir parent if missing."""
        if not self.path:
            return
        path_obj = Path(self.path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.graph)

        def _json_serial(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)

        with open(path_obj, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=_json_serial)

    def load(self) -> None:
        """Load from self.path if exists."""
        if not self.path:
            return
        path_obj = Path(self.path)
        if not path_obj.exists():
            return
        with open(path_obj, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.graph = nx.node_link_graph(data, directed=True)
        for nid in list(self.graph.nodes):
            if "node_id" not in self.graph.nodes[nid]:
                self.graph.nodes[nid]["node_id"] = str(nid)

    def stats(self) -> dict:
        """Return {node_count, edge_count, active_count, orphan_count, relationship_counts: dict}."""
        node_count = self.graph.number_of_nodes()
        edge_count = self.graph.number_of_edges()

        active_count = sum(
            1 for nid in self.graph.nodes if self.graph.nodes[nid].get("deletion_state") == "active"
        )
        orphan_count = sum(1 for nid in self.graph.nodes if self.graph.degree(nid) == 0)

        relationship_counts: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            rel = data.get("relationship", "unknown")
            relationship_counts[rel] = relationship_counts.get(rel, 0) + 1

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "active_count": active_count,
            "orphan_count": orphan_count,
            "relationship_counts": relationship_counts,
        }

