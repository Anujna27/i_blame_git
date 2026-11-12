"""Repeatable benchmark for hybrid context retrieval."""
import argparse, json, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.agent_a import AgentA

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--sessions",type=int,default=30); parser.add_argument("--token-budget",type=int,default=500); args=parser.parse_args()
    agent=AgentA()
    for i in range(args.sessions): agent.remember(f"Session {i} prefers Python and uses service {i}", session_id=f"bench_{i}")
    rows=[]
    for query in ["preferred programming language", "which service is used", "session context"]:
        start=time.perf_counter(); context=agent.build_active_context(query,args.token_budget); rows.append({"query":query,"entities":len(context.entities),"tokens":context.token_count,"latency_ms":round((time.perf_counter()-start)*1000,3)})
    print(json.dumps({"sessions":args.sessions,"token_budget":args.token_budget,"results":rows},indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
