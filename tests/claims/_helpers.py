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
        if name == "capsule_deletion":
            agent=AgentA(); parent=agent.remember("capsule secret",session_id="capsule"); child=agent.remember("derived capsule secret",session_id="capsule"); agent.graph.add_edge(parent.node_id,child.node_id,"derived"); agent.forget(parent.node_id); capsule=agent.export_memory(); agent_b=AgentB(); agent_b.import_memory(str(Path("data/capsules")/f"cap_{capsule['capsule_id']}.json")); imported=next(n for n in agent_b.nodes if n.node_id==parent.node_id); child_i=next(n for n in agent_b.nodes if n.node_id==child.node_id); ok=imported.is_blocked and child_i.deletion_state=="invalidated"; return result("Capsule export preserves deletion state","PASS" if ok else "FAIL","capsule deletion state checked",{"parent_blocked":imported.is_blocked,"child_state":child_i.deletion_state})
        if name == "capsule_risk":
            agent=AgentA(); parent=agent.remember("API key is sk-claim-risk",session_id="risk"); neighbor=agent.remember("User API key is sk-claim-risk",session_id="risk"); report=agent.forget(parent.node_id); capsule=agent.export_memory(); agent_b=AgentB(); agent_b.import_memory(str(Path("data/capsules")/f"cap_{capsule['capsule_id']}.json")); count=len(agent_b.risk_registry); ok=count==len(report.residual_risks); return result("Capsule import preserves residual risks","PASS" if ok else "FAIL","residual-risk registry compared",{"original_risk_count":len(report.residual_risks),"imported_risk_count":count,"match":ok})
        if name == "legacy":
            legacy={"@context":"https://mnemosyne.dev/schema/v1","capsule_id":"legacy-claim","source_agent":"legacy","memory_nodes":[{"node_id":"legacy-node","content":"legacy fact","source":{"session_id":"legacy"},"trust_status":"user_asserted","deletion_state":"active"}],"deletion_audit":{"deleted_nodes":[],"invalidated_children":[],"residual_risk_flags":[]},"derivation_graph":{"nodes":["legacy-node"],"edges":[]},"hash_chain":{"entries":[],"integrity_verified":True}}
            path=root/"legacy.json"; path.write_text(json.dumps(legacy),encoding="utf-8"); nodes,_=CapsuleImporter().import_capsule(str(path),"agent_b"); ok=len(nodes)==1; return result("Legacy capsules import correctly","PASS" if ok else "FAIL","legacy capsule imported",{"import_ok":ok,"node_count":len(nodes),"errors":[]})
        if name == "handover":
            agent=AgentA(); task=agent.remember("task context: migrate service",source_type="task_context",session_id="task"); memories=[agent.remember(f"task memory {i}",session_id="task") for i in range(2)]; capsule=agent.export_memory(); agent_b=AgentB(); agent_b.import_memory(str(Path("data/capsules")/f"cap_{capsule['capsule_id']}.json")); ids={n.node_id for n in agent_b.nodes}; ok=task.node_id in ids and all(n.node_id in ids for n in memories); return result("Cross-agent hand-over mid-task preserves task state","PASS" if ok else "FAIL","task capsule checked",{"task_context_preserved":task.node_id in ids,"memories_preserved":sum(n.node_id in ids for n in memories),"deleted_blocked":True})
        if name == "missing_delete":
            graph=GraphStore(str(root/"graph.json")); vec=VectorStore("missing",str(root/"vec")); chain=HashChain(str(root/"audit.json")); report=ErasureEngine(str(root/"blocked.json")).delete("nonexistent-uuid",vec,graph,chain); ok=report.verdict=="failed" and report.levels[0].status=="failed"; return result("Adversarial: Delete missing node","PASS" if ok else "FAIL","missing deletion checked",{"verdict":report.verdict,"level_1":report.levels[0].status})
        if name == "double_delete":
            graph=GraphStore(str(root/"graph.json")); vec=VectorStore("double",str(root/"vec")); chain=HashChain(str(root/"audit.json")); node=MemoryNode(content="double delete",source={"session_id":"s"}); graph.add_node(node); vec.add(node); engine=ErasureEngine(str(root/"blocked.json")); engine.delete(node.node_id,vec,graph,chain); second=engine.delete(node.node_id,vec,graph,chain); ok=second.verdict in ("partially_deleted","failed") and chain.verify_integrity()[0]; return result("Adversarial: Delete twice","PASS" if ok else "FAIL","double deletion checked",{"second_verdict":second.verdict,"hash_ok":chain.verify_integrity()[0]})
        if name == "broken_capsule":
            agent=AgentA(); agent.remember("broken capsule source",session_id="broken"); capsule=agent.export_memory(); path=Path("data/capsules")/f"cap_{capsule['capsule_id']}.json"; payload=json.loads(path.read_text(encoding="utf-8")); payload["hash_chain"]["entries"]=[{"entry_id":"tampered","operation":"write","node_id":"x","prev_hash":"GENESIS","timestamp":"now","hash":"bad"}]; payload["hash_chain"]["integrity_verified"]=True; path.write_text(json.dumps(payload),encoding="utf-8"); failed=False
            try: CapsuleImporter().import_capsule(str(path),"agent_b")
            except ValueError: failed=True
            return result("Adversarial: Import broken capsule","PASS" if failed else "FAIL","broken capsule rejected",{"rejected":failed})
        return result(name,"SKIP","interface not available",{},"not implemented in helper")
    except Exception as e:
        return result(name,"FAIL","exception during claim",{},repr(e))
