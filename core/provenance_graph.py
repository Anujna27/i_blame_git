# STUB — waiting for M1/M2/M3
class ProvenanceGraph:
    def __init__(self): self.nodes = {}; self.edges = {}
    def add_node(self, node): self.nodes[node.node_id] = node
    def add_edge(self, parent_id, child_id, edge_type="derived"): self.edges.setdefault(parent_id, []).append((child_id, edge_type))
    def get_node(self, node_id): return self.nodes.get(node_id)
    def get_descendants(self, node_id): return [self.nodes[c] for c, _ in self.edges.get(node_id, []) if c in self.nodes]
    def get_ancestors(self, node_id): return [self.nodes[p] for p, es in self.edges.items() if any(c == node_id for c, _ in es) and p in self.nodes]
    def get_orphaned_children(self, node_id): return self.get_descendants(node_id)
    def get_all_active_nodes(self): return [n for n in self.nodes.values() if n.deletion_state == "active"]
    def persist(self): return None
