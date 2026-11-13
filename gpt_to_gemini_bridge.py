import os
from google import genai
from agents.agent_a import AgentA

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
agent = AgentA()

def ask_gemini(query):
    result = agent.recall(query)
    memory_context = result.get("answer", "No memory found.")
    print("\n--- MEMORY RETRIEVED FROM MNEMOSYNE ---")
    print(memory_context[:300] + "...\n")
    
    prompt = f"Use the memory context to answer:\nContext: {memory_context}\nQuestion: {query}"
    
    models = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.6-flash"]
    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            print(f"=== GEMINI RESPONSE ({model}) ===")
            print(response.text)
            return
        except Exception as e:
            pass
    print("All models are currently busy. But the memory retrieval worked!")

if __name__ == "__main__":
    ask_gemini("What pets did I say I like in my ChatGPT history?")
