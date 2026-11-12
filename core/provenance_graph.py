import json
import os
from pathlib import Path
import networkx as nx
from .memory_node import MemoryNode


class ProvenanceGraph:
    def __init__(self, path="data/provenance_graph.json"):
        self.path = path
        self.graph = nx.DiGraph()
        self.nodes = {}
        if os.path.exists(path):
            self.load()

    def add_node(self, node):
        self.nodes[node.node_id] = node
        self.graph.add_node(node.node_id)
        for edge in node.derivation_edges:
            self.graph.add_edge(node.node_id, edge["child_id"], type=edge["type"])
        self.persist()

    def add_edge(self, parent_id, child_id, edge_type):
        self.graph.add_edge(parent_id, child_id, type=edge_type)
        if parent_id in self.nodes:
            self.nodes[parent_id].add_derivation(child_id, edge_type)
        self.persist()

    def get_node(self, node_id): return self.nodes.get(node_id)
    def get_descendants(self, node_id):
        return list(nx.descendants(self.graph, node_id)) if node_id in self.graph else []
    def get_ancestors(self, node_id):
        return list(nx.ancestors(self.graph, node_id)) if node_id in self.graph else []

    def get_orphaned_children(self, node_id):
        return [x for x in self.get_descendants(node_id) if self.nodes.get(x) and self.nodes[x].deletion_state == "active"
                and any(self.nodes.get(p) and self.nodes[p].deletion_state != "active" for p in self.graph.predecessors(x))]

    def find_orphans(self):
        return [n.node_id for n in self.get_all_active_nodes()
                if any(self.nodes.get(p) and self.nodes[p].deletion_state != "active"
                       for p in self.graph.predecessors(n.node_id))]

    def heal_orphans(self, actor="graph-healer"):
        """Reattach orphaned entities to their nearest active ancestor when possible."""
        healed = []
        for node_id in self.find_orphans():
            node = self.nodes[node_id]
            active_ancestors = [a for a in nx.ancestors(self.graph, node_id)
                                if self.nodes.get(a) and self.nodes[a].deletion_state == "active"]
            if active_ancestors:
                parent = active_ancestors[-1]
                self.graph.add_edge(parent, node_id, type="healed_provenance")
                self.nodes[parent].add_derivation(node_id, "healed_provenance")
                healed.append({"node_id": node_id, "parent_id": parent})
            else:
                node.record_lifecycle_event("quarantined", actor, "no active provenance root")
                healed.append({"node_id": node_id, "parent_id": None})
        if healed: self.persist()
        return healed

    def get_all_active_nodes(self): return [n for n in self.nodes.values() if n.deletion_state == "active"]
    def get_deleted_nodes(self): return [n for n in self.nodes.values() if n.deletion_state != "active"]

    def persist(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        payload = {"graph": nx.node_link_data(self.graph, edges="edges"), "nodes": {k: v.to_jsonld() for k, v in self.nodes.items()}}
        with open(self.path, "w", encoding="utf-8") as f: json.dump(payload, f, indent=2, default=str)

    def load(self):
        if not os.path.exists(self.path): return
        with open(self.path, "r", encoding="utf-8") as f: payload = json.load(f)
        if "graph" in payload and "nodes" in payload:
            graph_data = payload["graph"]
            edge_key = "edges" if "edges" in graph_data else "links"
            self.graph = nx.node_link_graph(graph_data, directed=True, edges=edge_key)
            self.nodes = {k: MemoryNode.from_jsonld(v) for k, v in payload["nodes"].items()}
