"""Compatibility import for clients migrating to KnowledgeGraph.

New code must import ``KnowledgeGraph`` from ``core.knowledge_graph``.
"""
from .knowledge_graph import KnowledgeGraph

ProvenanceGraph = KnowledgeGraph

__all__ = ["KnowledgeGraph", "ProvenanceGraph"]
