from typing import Optional

from core.memory_node import MemoryNode
from core.provenance_graph import ProvenanceGraph


class GraphStore:
    """Wrapper around ProvenanceGraph providing persistent graph storage for MemoryNodes."""

    def __init__(self, path: str = "data/provenance_graph.json"):
        self._provenance = ProvenanceGraph(path=path)

    @property
    def graph(self):
        return self._provenance.graph

    @property
    def nodes(self) -> dict[str, MemoryNode]:
        return self._provenance.nodes

    def add_node(self, node: MemoryNode) -> None:
        """Add a MemoryNode to the provenance graph and persist."""
        self._provenance.add_node(node)

    def add_edge(self, parent_id: str, child_id: str, edge_type: str) -> None:
        """Add a directed provenance edge between two nodes and persist."""
        self._provenance.add_edge(parent_id, child_id, edge_type)

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        """Return the MemoryNode for node_id if present."""
        return self._provenance.get_node(node_id)

    def get_descendants(self, node_id: str) -> list[str]:
        """Return descendant node IDs reachable from node_id."""
        return self._provenance.get_descendants(node_id)

    def get_ancestors(self, node_id: str) -> list[str]:
        """Return ancestor node IDs reaching node_id."""
        return self._provenance.get_ancestors(node_id)

    def get_orphaned_children(self, node_id: str) -> list[str]:
        """Return active descendants whose parent was deleted."""
        return self._provenance.get_orphaned_children(node_id)

    def get_all_active_nodes(self) -> list[MemoryNode]:
        """Return all active (non-deleted) MemoryNodes in the graph."""
        return self._provenance.get_all_active_nodes()

    def get_deleted_nodes(self) -> list[MemoryNode]:
        """Return all soft-deleted or invalidated MemoryNodes in the graph."""
        return self._provenance.get_deleted_nodes()

    def persist(self) -> None:
        """Persist the provenance graph state to disk."""
        self._provenance.persist()

    def load(self) -> None:
        """Reload the provenance graph state from disk."""
        self._provenance.load()

