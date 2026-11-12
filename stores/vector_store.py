# STUB — waiting for M1/M2/M3
class VectorStore:
    def __init__(self): self.nodes={}
    def add(self,node,embedding=None): self.nodes[node.node_id]=node
    def remove(self,node_id): self.nodes.pop(node_id,None)
    def remove_from_active_index(self,node_id): self.nodes.pop(node_id,None)
    def query(self,query_text_or_embedding,top_k=5):
        terms=set(str(query_text_or_embedding).lower().split()); scored=[]
        for n in self.nodes.values(): scored.append((len(terms & set(n.content.lower().split())), n))
        return [n for score,n in sorted(scored,key=lambda x:x[0],reverse=True)[:top_k] if score or len(scored) <= top_k]
    def get_by_id(self,node_id): return self.nodes.get(node_id)
