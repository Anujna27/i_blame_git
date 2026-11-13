import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from agents import AgentA


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


GEMINI_PATH = Path("data/gemini_import/gemini_chat.json")


def ingest_gemini(path=GEMINI_PATH):
    raw = Path(path).read_text(encoding="utf-8").strip()
    data = json.loads(raw) if raw else {}
    chats = data.get("chat", [])
    if not chats:
        print("Warning: no chats found in data/gemini_import/gemini_chat.json")
    agent = AgentA()

    processed_turns = 0
    for index, turn in enumerate(chats, start=1):
        user_text = turn.get("user", "")
        ai_html = turn.get("ai", "")
        if user_text:
            agent.remember(content=user_text, source_type="gemini_user", session_id="gemini_bridge")
        if ai_html:
            clean_text = BeautifulSoup(ai_html, "html.parser").get_text(" ", strip=True)
            if clean_text:
                agent.remember(content=clean_text, source_type="gemini_ai", session_id="gemini_bridge")
        processed_turns += 1
        print(f"Processed Gemini turn {index}/{len(chats)}")

    agent.vector_store._persist()
    agent.graph.persist()
    # HashChain.append() persists each audit entry immediately; no save() method exists.
    print(f"✅ Gemini ingestion complete: {processed_turns} turns processed")
    return agent


if __name__ == "__main__":
    ingest_gemini()
