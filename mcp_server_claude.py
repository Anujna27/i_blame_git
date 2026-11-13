from mcp.server.fastmcp import FastMCP

from agents.agent_a import AgentA


mcp = FastMCP("Mnemosyne")
agent = AgentA()


@mcp.tool()
def search_memory(query: str) -> str:
    """Searches the ingested Gemini history for relevant context."""
    result = agent.recall(query=query)
    return result.get("answer", "No memory found.")


if __name__ == "__main__":
    mcp.run()
