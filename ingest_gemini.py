import html
import json
import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from agents import AgentA


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


GEMINI_PATH = ROOT_DIR / "data" / "gemini_import" / "gemini_chat.json"


def clean_html(raw_html: str) -> str:
    """Extract clean text from HTML using BeautifulSoup or standard library fallback."""
    if not raw_html:
        return ""
    if BeautifulSoup is not None:
        try:
            return BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
        except Exception:
            pass
    text = re.sub(r"<[^>]+>", " ", raw_html)
    return html.unescape(" ".join(text.split()))


def ingest_gemini(path=GEMINI_PATH):
    p = Path(path)
    if not p.exists():
        print(f"Error: Gemini chat file not found at {p.resolve()}")
        print("Please place the Gemini export at 'data/gemini_import/gemini_chat.json'.")
        return None

    raw = p.read_text(encoding="utf-8").strip()
    data = json.loads(raw) if raw else {}
    chats = data.get("chat", [])
    if not chats:
        print(f"Warning: no chats found in {path}")
        return None

    agent = AgentA()

    processed_turns = 0
    for index, turn in enumerate(chats, start=1):
        user_text = turn.get("user", "")
        ai_html = turn.get("ai", "")
        if user_text:
            agent.remember(
                content=user_text,
                source_type="gemini_user",
                session_id="gemini_bridge",
                turn_index=index * 2 - 1,
            )
        if ai_html:
            clean_text = clean_html(ai_html)
            if clean_text:
                agent.remember(
                    content=clean_text,
                    source_type="gemini_ai",
                    session_id="gemini_bridge",
                    turn_index=index * 2,
                )
        processed_turns += 1
        print(f"Processed Gemini turn {index}/{len(chats)}")

    agent.vector_store._persist()
    agent.graph.persist()
    # HashChain.append() persists each audit entry immediately; no save() method exists.
    print(f"✅ Gemini ingestion complete: {processed_turns} turns processed")
    return agent


if __name__ == "__main__":
    # If run outside the project virtual environment, automatically switch to it
    venv_python = ROOT_DIR / "venv" / "Scripts" / "python.exe"
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        import subprocess
        sys.exit(subprocess.call([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:]))

    target_path = sys.argv[1] if len(sys.argv) > 1 else GEMINI_PATH
    ingest_gemini(target_path)
