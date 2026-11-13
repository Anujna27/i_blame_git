from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents import AgentA


app = FastAPI(title="MNEMOSYNE Memory Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
agent_a = AgentA()


class SearchQuery(BaseModel):
    query: str


@app.post("/search_memory")
def search_memory(payload: SearchQuery):
    result = agent_a.recall(query=payload.query)
    return {"answer": result.get("answer", "No memory found.")}
