import json
import sys
from pathlib import Path

from agents.agent_a import AgentA


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


CONVERSATIONS_PATH = Path("data/gpt_import/conversations.json")


def ingest_chatgpt(path=CONVERSATIONS_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    agent = AgentA()
    processed_messages = 0

    if isinstance(data, dict) and "messages" in data:
        for message in data.get("messages", []):
            role = message.get("role")
            text = message.get("say", "")
            if role not in {"Prompt", "Response"} or not text:
                continue
            source_type = "chatgpt_user" if role == "Prompt" else "chatgpt_ai"
            agent.remember(content=text, source_type=source_type, session_id="gpt_bridge")
            processed_messages += 1
    else:
        conversations = data if isinstance(data, list) else data.get("conversations", [])
        for conversation in conversations:
            mapping = conversation.get("mapping", {})
            for mapped_message in mapping.values():
                message = mapped_message.get("message") if isinstance(mapped_message, dict) else None
                if not message:
                    continue
                role = message.get("author", {}).get("role")
                parts = message.get("content", {}).get("parts", [])
                text = parts[0] if parts and isinstance(parts[0], str) else ""
                if not text or role not in {"user", "assistant"}:
                    continue
                source_type = "chatgpt_user" if role == "user" else "chatgpt_ai"
                agent.remember(content=text, source_type=source_type, session_id="gpt_bridge")
                processed_messages += 1

    agent.vector_store._persist()
    agent.graph.persist()
    print(f"✅ ChatGPT ingestion complete: {processed_messages} messages processed")
    return agent


if __name__ == "__main__":
    ingest_chatgpt()
