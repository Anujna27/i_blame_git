"""Public knowledge-graph API.

The implementation remains in provenance_graph.py for storage compatibility;
new code should import KnowledgeGraph from this module.
"""
from .provenance_graph import KnowledgeGraph

__all__ = ["KnowledgeGraph"]
