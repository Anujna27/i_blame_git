"""Persistent graph-healing worker entry point."""
import argparse, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.agent_a import AgentA

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--interval",type=int,default=900); parser.add_argument("--once",action="store_true")
    args=parser.parse_args(); agent=AgentA()
    if args.once: print(agent.build_knowledge_graph()); return 0
    agent.start_graph_healing(args.interval); print(f"Healing worker running every {args.interval}s. Press Ctrl+C to stop.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        agent.stop_graph_healing(); return 0
if __name__ == "__main__": raise SystemExit(main())
