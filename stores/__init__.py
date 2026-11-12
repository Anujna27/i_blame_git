"""Stores package with lazy exports to avoid circular / DLL initialization conflicts."""

def __getattr__(name):
    if name == "GraphStore":
        from .graph_store import GraphStore
        return GraphStore
    if name == "SessionStore":
        from .session_store import SessionStore
        return SessionStore
    if name == "VectorStore":
        from .vector_store import VectorStore
        return VectorStore
    if name == "KnowledgeGraph":
        from core.knowledge_graph import KnowledgeGraph
        return KnowledgeGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["GraphStore", "KnowledgeGraph", "VectorStore", "SessionStore"]
