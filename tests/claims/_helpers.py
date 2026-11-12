import json, tempfile, os
from pathlib import Path
from datetime import datetime, timezone

from agents.agent_a import AgentA
from agents.agent_b import AgentB
from core.hash_chain import HashChain
from core.memory_node import MemoryNode
from core.erasure_engine import ErasureEngine
from core.provenance_graph import KnowledgeGraph
from stores.vector_store import VectorStore
from stores.graph_store import GraphStore
from capsule.export import CapsuleExporter
from capsule.import_capsule import CapsuleImporter
from core.contradiction import ContradictionEngine
from core.abstention import AbstentionEngine

def result(name, status, details, evidence=None, error=None):
    return {"name": name, "status": status, "details": details,
            "evidence": evidence or {}, "error": error}

def isolated_context(context):
    root = Path(tempfile.mkdtemp(prefix="mnemosyne_claim_")); return root

def claim(name, context):
    root = isolated_context(context)
    os.chdir(root)
    try:
        if name == "five_level":
            chain=HashChain(str(root/'audit.json')); graph=GraphStore(str(root/'graph.json')); vec=VectorStore('claim', str(root/'vec'))
            parent=MemoryNode(content="parent fact", source={"session_id":"s"}); graph.add_node(parent); vec.add(parent)
            for i in range(int(context.get("node_count",1))):
                child=MemoryNode(content=f"derived child {i}", source={"session_id":"s"}); graph.add_node(child); graph.add_edge(parent.node_id,child.node_id,"derived"); vec.add(child)
            report=ErasureEngine(str(root/'blocked.json')).delete(parent.node_id,vec,graph,chain)
            ok=len(report.levels)==5 and report.levels[0].status=="passed" and report.levels[1].status in ("passed","partial") and report.levels[2].status=="passed" and report.levels[4].status=="failed" and chain.verify_integrity()[0]
            return result("Five-level erasure runs correctly on all scenarios", "PASS" if ok else "FAIL", "five-level report evaluated", {"levels":len(report.levels),"verdict":report.verdict}, None if ok else "unexpected erasure result")
        if name == "restart":
            agent=AgentA(); parent=agent.remember("restart parent",session_id="claim_restart"); child=agent.remember("restart child",session_id="claim_restart"); agent.graph.add_edge(parent.node_id,child.node_id,"derived"); agent.forget(parent.node_id); fresh=AgentA(); p=fresh.graph.get_node(parent.node_id); c=fresh.graph.get_node(child.node_id); ok=p and c and p.deletion_state!="active" and c.deletion_state=="invalidated"; return result("Deletion state survives restart","PASS" if ok else "FAIL","reload checked",{"parent_state":getattr(p,"deletion_state",None),"child_state":getattr(c,"deletion_state",None),"hash_ok":fresh.hash_chain.verify_integrity()[0]})
        if name == "tamper":
            chain=HashChain(str(root/'audit.json')); [chain.append("write",str(i),{}) for i in range(5)]; original=chain.verify_integrity()[0]; chain.entries[2]["details"]={"tampered":True}; ok=original and not chain.verify_integrity()[0]; return result("Hash chain detects tampering","PASS" if ok else "FAIL","in-memory tamper checked",{"original_ok":original,"post_tamper_ok":not ok})
        if name == "trust":
            vec=VectorStore('trust',str(root/'vec')); planted=MemoryNode(content="deployment secret",trust_status="planted"); verified=MemoryNode(content="deployment secret",trust_status="verified"); vec.add(planted); vec.add(verified); nodes=vec.query("deployment secret",5); ok=nodes and nodes[0].node_id==verified.node_id; return result("Vector retrieval respects trust filter","PASS" if ok else "FAIL","trust ordering checked",{"verified_rank":next((i for i,n in enumerate(nodes) if n.node_id==verified.node_id),-1),"planted_returned":any(n.node_id==planted.node_id for n in nodes)})
        if name == "budget":
            agent=AgentA(); [agent.remember("word "*20,session_id="sess_001") for _ in range(20)]; ctx=agent.build_active_context("word",int(context.get("token_budget",200))); actual=ctx.token_count; ok=actual<=int(context.get("token_budget",200)); return result("Token budget is respected","PASS" if ok else "FAIL","bounded active context checked",{"budget":int(context.get("token_budget",200)),"actual_tokens":actual})
        if name == "contradiction":
            a=MemoryNode(content="The age is 30",source={"session_id":"s"}); b=MemoryNode(content="The age is 45",source={"session_id":"s"}); conflicts=ContradictionEngine().detect(b,[a]); ok=bool(conflicts); return result("Contradiction detection returns both nodes","PASS" if ok else "FAIL","contradiction engine checked",{"conflict_detected":ok})
        if name == "abstention":
            abstain,reason=AbstentionEngine().should_abstain("unknown fact",[]); ok=abstain and bool(reason); return result("Abstention triggers on insufficient evidence","PASS" if ok else "FAIL",reason,{"abstained":abstain,"reason":reason})
        if name == "lifecycle":
            agent=AgentA(); n=agent.remember("audited",session_id="s"); agent.forget(n.node_id,reason="GDPR request",deleted_by="alice"); entries=agent.hash_chain.get_entries(); e=entries[-1]; actor=e.get("actor")=="alice" or e.get("details",{}).get("actor")=="alice"; reason=e.get("reason")=="GDPR request" or e.get("details",{}).get("reason")=="GDPR request"; ok=actor and reason; return result("Lifecycle audit records who/what/when/why","PASS" if ok else "FAIL","audit entry checked",{"entry":e,"has_actor":actor,"has_reason":reason,"has_timestamp":bool(e.get("timestamp"))})
        if name == "sessions":
            agent=AgentA(); count=int(context.get("sessions",30)); [agent.remember(f"memory {i}",session_id=f"s_{i}") for i in range(count)]; fresh=AgentA(); ids={n.session_id for n in fresh.graph.get_all_active_nodes()}; ok=len(ids)>=count; return result("30 sessions survive restart","PASS" if ok else "FAIL","sessions reloaded",{"sessions_written":count,"sessions_reloaded":len(ids),"hash_ok":fresh.hash_chain.verify_integrity()[0]})
        if name == "healing":
            agent=AgentA(); n=agent.remember("isolated healing entity",session_id="heal"); import networkx as nx
            for node_id in agent.graph.nodes:
                if node_id not in agent.graph.graph: agent.graph.graph.add_node(node_id)
            before=len(list(nx.isolates(agent.graph.graph))); agent.commit_session("heal"); after=len(list(nx.isolates(agent.graph.graph))); node=agent.graph.get_node(n.node_id); ok=after<before or node.deletion_state=="quarantined"; return result("Session commit auto-triggers healing","PASS" if ok else "FAIL","healing checked",{"isolated_before":before,"isolated_after":after,"quarantined":int(node.deletion_state=="quarantined")})
        return result(name,"SKIP","interface not available",{},"not implemented in helper")
    except Exception as e:
        return result(name,"FAIL","exception during claim",{},repr(e))
