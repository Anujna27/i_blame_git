"""
GraphStore — Person 2's contract surface.

PRODUCES:
    add_entity(node) -> dict
    add_relationship(source_id, target_id, relationship, metadata=None) -> dict
    remove_entity_edges(node_id) -> int
    get_entity(node_id) -> dict | None
    get_neighbors(node_id, relationship=None, direction="out") -> list[dict]
    get_related_entities(node_id, max_hops=2, relationship=None) -> list[dict]
    get_all_active_entities() -> list[dict]
    find_orphans(session_id=None) -> list[OrphanRecord]
    heal_orphans(session_id=None) -> HealingReport
    find_duplicates(threshold=0.95) -> list[DuplicatePair]
    on_session_commit(session_id) -> dict
    stats() -> dict

CONSUMES:
    vector_store: exposes .query(query_text, top_k). Results expose
        .node_id/.score OR dict keys "node_id"/"score". Missing or
        malformed shapes fall back to Jaccard similarity. Never crashes.
    audit_chain: exposes .append(operation, node_id, details).
        None or malformed is silently skipped. Never crashes.

INVARIANTS:
    - No silent merges. Duplicates reported, not merged.
    - No auto-delete. Orphans quarantined, never removed.
    - Every mutation persists immediately.
    - Reads never persist.
    - on_session_commit never raises.
"""

from typing import Any, Optional
import warnings

import networkx as nx

from core.graph_healer import GraphHealer, HealingReport
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode


class GraphStore:
    """Unified Graph Store interface wrapping KnowledgeGraph and GraphHealer.

    Serves Person 3 (context builder), Person 4 (UI), and Person 1 (session commit hook).
    """

    def __init__(
        self,
        path: str = "data/knowledge_graph.json",
        vector_store: Any = None,
        audit_chain: Any = None,
        similarity_threshold: float = 0.82,
        llm_suggester: Any = None,
    ):
        self.path = path
        self.kg = KnowledgeGraph(path=path)
        self.healer = GraphHealer(
            graph=self.kg,
            vector_store=vector_store,
            audit_chain=audit_chain,
            similarity_threshold=similarity_threshold,
            llm_suggester=llm_suggester,
        )
        self._memory_nodes: dict[str, MemoryNode] = {}

    # --- Person 2 Contract Methods ---

    def add_entity(self, node: Any) -> dict:
        """Add or update an entity in the knowledge graph and persist."""
        if isinstance(node, MemoryNode):
            self._memory_nodes[node.node_id] = node
        stored = self.kg.add_entity(node)
        self.kg.persist()
        return stored

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Add typed relationship between two entities and persist."""
        attrs = self.kg.add_relationship(source_id, target_id, relationship, metadata=metadata)
        self.kg.persist()
        return attrs

    def remove_entity_edges(self, node_id: str, persist: bool = True) -> int:
        """Remove all incident edges on node_id and persist."""
        count = self.kg.remove_entity_edges(node_id, persist=persist)
        if persist:
            self.kg.persist()
        return count

    def get_entity(self, node_id: str) -> Optional[dict]:
        """Fetch canonical entity dict or None."""
        return self.kg.get_entity(node_id)

    def get_neighbors(
        self,
        node_id: str,
        relationship: Optional[str] = None,
        direction: str = "out",
    ) -> list[dict]:
        """Fetch neighbor entity dicts filtered by relationship and direction."""
        return self.kg.get_neighbors(node_id, relationship=relationship, direction=direction)

    def get_related_entities(
        self,
        node_id: str,
        max_hops: int = 2,
        relationship: Optional[str] = None,
    ) -> list[dict]:
        """BFS traversal up to max_hops returning unique connected entities."""
        return self.kg.get_related_entities(node_id, max_hops=max_hops, relationship=relationship)

    def get_all_active_entities(self) -> list[dict]:
        """Fetch all entities with deletion_state == 'active'."""
        return self.kg.get_active_entities()

    def find_orphans(self, session_id: Optional[str] = None) -> list:
        """Find orphan records globally or scoped to a session."""
        return self.healer.find_orphans(session_id=session_id)

    def heal_orphans(self, session_id: Optional[str] = None) -> HealingReport:
        """Run orphan healing pipeline and persist graph mutations."""
        report = self.healer.heal_orphans(session_id=session_id)
        self.kg.persist()
        return report

    def find_duplicates(self, threshold: float = 0.95):
        """Delegate to self.healer.find_duplicates. Read-only, no persist."""
        return self.healer.find_duplicates(threshold=threshold)

    def merge_duplicate(self, keep_node_id: str, remove_node_id: str, actor="system", reason="explicit_duplicate_merge"):
        return self.healer.merge_duplicate(keep_node_id, remove_node_id, actor, reason)

    def on_session_commit(self, session_id: str) -> dict:
        """Hook called by Person 1's agent.commit_session().

        Runs orphan healing for the committed session and persists the graph.
        Never lets a healing error crash the commit flow.
        """
        try:
            report = self.healer.heal_orphans(session_id=session_id)
            self.kg.persist()
            return {
                "session_id": session_id,
                "orphans_found": len(report.orphans_found),
                "healed_count": report.healed_count,
                "quarantined": report.quarantined,
                "actions": [a.__dict__ for a in report.actions_taken],
            }
        except Exception as e:
            warnings.warn(f"on_session_commit healing failed: {e}", UserWarning, stacklevel=2)
            try:
                self.kg.persist()
            except Exception:
                pass
            return {
                "session_id": session_id,
                "orphans_found": -1,
                "error": str(e),
            }

    def stats(self) -> dict:
        """Return graph node, edge, active, orphan, and relationship counts."""
        return self.kg.stats()

    # --- Backward Compatibility Methods for Core Engine / Contradiction Engine ---

    @property
    def graph(self):
        return self.kg.graph

    def add_node(self, node: MemoryNode) -> None:
        self._memory_nodes[node.node_id] = node
        self.kg.add_entity(node)
        self.kg.persist()

    def add_edge(self, parent_id: str, child_id: str, edge_type: str = "DERIVED_FROM") -> None:
        rel = edge_type.upper()
        if rel == "DERIVED":
            rel = "DERIVED_FROM"
        elif rel not in (
            "PREFERS",
            "OWNS",
            "EXTRACTED_FROM",
            "DERIVED_FROM",
            "CONTRADICTS",
            "RELATED_TO",
            "SESSION_MEMBER",
            "MENTIONS",
        ):
            rel = "RELATED_TO"
        try:
            self.kg.add_relationship(parent_id, child_id, rel)
            self.kg.persist()
        except Exception:
            pass

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        if node_id in self._memory_nodes:
            return self._memory_nodes[node_id]
        ent = self.kg.get_entity(node_id)
        if ent:
            try:
                return MemoryNode.from_jsonld(ent)
            except Exception:
                pass
        return None

    def get_descendants(self, node_id: str) -> list[str]:
        if not self.kg.graph.has_node(node_id):
            return []
        return list(nx.descendants(self.kg.graph, node_id))

    def get_ancestors(self, node_id: str) -> list[str]:
        if not self.kg.graph.has_node(node_id):
            return []
        return list(nx.ancestors(self.kg.graph, node_id))

    def get_all_active_nodes(self) -> list[MemoryNode]:
        result = []
        for ent in self.kg.get_active_entities():
            nid = ent["node_id"]
            if nid in self._memory_nodes:
                result.append(self._memory_nodes[nid])
            else:
                try:
                    result.append(MemoryNode.from_jsonld(ent))
                except Exception:
                    pass
        return result

    def get_deleted_nodes(self) -> list[MemoryNode]:
        result = []
        for nid, data in self.kg.graph.nodes.items():
            if data.get("deletion_state") != "active":
                if nid in self._memory_nodes:
                    result.append(self._memory_nodes[nid])
                else:
                    try:
                        result.append(MemoryNode.from_jsonld(dict(data)))
                    except Exception:
                        pass
        return result

    def persist(self) -> None:
        self.kg.persist()

    def load(self) -> None:
        self.kg.load()
