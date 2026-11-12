# STUB — waiting for M1/M2/M3
from core.provenance_graph import ProvenanceGraph
class GraphStore(ProvenanceGraph):
    def get_deleted_nodes(self): return [n for n in self.nodes.values() if n.deletion_state != "active"]
