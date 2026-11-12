"""FAISS-backed VectorStore for M1 integration testing.
Implements the ErasureEngine contract without touching stores/.
"""
import json
from pathlib import Path
from typing import Optional
import numpy as np
import faiss
from core.memory_node import MemoryNode

def _simple_embed(text: str, dim: int = 64) -> np.ndarray:
    vec = np.zeros(dim, dtype="float32")
    for i, ch in enumerate(text.lower()): vec[i % dim] += (ord(ch) % 32) / 32.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec

class FaissVectorStore:
    def __init__(self, collection_name="faiss_test", persist_dir="data/faiss_test"):
        self.collection_name=collection_name; self.persist_dir=Path(persist_dir); self.persist_dir.mkdir(parents=True,exist_ok=True)
        self.dim=64; self.index=faiss.IndexFlatL2(self.dim); self.nodes={}; self.id_to_pos={}; self.blocked=set(); self._load_if_exists()
    def _load_if_exists(self):
        p=self.persist_dir/f"{self.collection_name}_meta.json"
        if p.exists():
            with p.open(encoding="utf-8") as f: data=json.load(f)
            for d in data.get("nodes",[]):
                n=MemoryNode.from_jsonld(d); self.nodes[n.node_id]=n
            self.blocked.update(data.get("blocked",[]))
            for n in self.nodes.values():
                self.index.add(_simple_embed(n.content,self.dim).reshape(1,-1)); self.id_to_pos[n.node_id]=self.index.ntotal-1
    def _persist(self):
        with (self.persist_dir/f"{self.collection_name}_meta.json").open("w",encoding="utf-8") as f: json.dump({"nodes":[n.to_jsonld() for n in self.nodes.values()],"blocked":list(self.blocked)},f,indent=2)
    def add(self,node):
        self.index.add(_simple_embed(node.content,self.dim).reshape(1,-1)); self.id_to_pos[node.node_id]=self.index.ntotal-1; self.nodes[node.node_id]=node; self._persist()
    def remove_from_active_index(self,node_id):
        if node_id in self.nodes: self.nodes[node_id].deletion_state="source_removed"
        self.blocked.add(node_id); self._persist()
    def query(self,query_text_or_embedding,top_k=5):
        if self.index.ntotal==0: return []
        q=_simple_embed(query_text_or_embedding,self.dim) if isinstance(query_text_or_embedding,str) else np.array(query_text_or_embedding,dtype="float32")
        _, indices=self.index.search(q.reshape(1,-1),min(top_k,self.index.ntotal)); reverse={v:k for k,v in self.id_to_pos.items()}; out=[]
        for idx in indices[0]:
            node_id=reverse.get(int(idx));
            if node_id and node_id not in self.blocked and node_id in self.nodes: out.append(self.nodes[node_id])
        return out
    def get_by_id(self,node_id) -> Optional[MemoryNode]: return self.nodes.get(node_id)
