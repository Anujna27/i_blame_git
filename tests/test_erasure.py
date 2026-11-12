import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from core.memory_node import MemoryNode
from core.hash_chain import HashChain
from core.erasure_engine import ErasureEngine
from core.residual_risk import ResidualRiskReporter

SRC={"type":"test","session_id":"s","turn_index":1,"timestamp":"2026-01-01T00:00:00","raw_reference":"r"}
class MockGraphStore:
    def __init__(self,nodes,children): self.nodes={n.node_id:n for n in nodes}; self.children=children
    def get_node(self,i): return self.nodes.get(i)
    def get_descendants(self,i): return self.children.get(i,[])
    def get_all_active_nodes(self): return [n for n in self.nodes.values() if n.deletion_state=="active"]
class MockVectorStore:
    def __init__(self,neighbors): self.neighbors=neighbors; self.removed=[]
    def remove_from_active_index(self,i): self.removed.append(i)
    def query(self,q,top_k=3): return self.neighbors[:top_k]
def test_erasure(tmp_path):
    parent=MemoryNode(content="User's API key is sk-abc123",source=SRC)
    children=[MemoryNode(content=f"Derived artifact {i} from {parent.content}",source=SRC) for i in range(3)]
    for c in children: parent.add_derivation(c.node_id,"derived")
    neighbor=MemoryNode(content="User API key is sk-abc123",source=SRC)
    graph=MockGraphStore([parent,*children,neighbor],{parent.node_id:[c.node_id for c in children]})
    vector=MockVectorStore([neighbor]); chain=HashChain(str(tmp_path/"audit.json"))
    report=ErasureEngine(str(tmp_path/"blocked.json")).delete(parent.node_id,vector,graph,chain)
    assert len(report.levels)==5; assert report.levels[0].status=="passed"; assert report.levels[1].status=="passed"; assert report.levels[2].status=="passed"; assert report.levels[3].status=="partial"; assert report.levels[4].status=="failed"; assert report.verdict=="partially_deleted"; assert len(report.residual_risks)>=1
    print(ResidualRiskReporter().generate_notice(report)); assert chain.verify_integrity()[0]
