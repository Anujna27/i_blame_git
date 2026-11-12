"""
DEPRECATED — do not use for new code.

All graph operations have moved to core/knowledge_graph.py and
stores/graph_store.py. ProvenanceGraph is a thin alias that emits
a DeprecationWarning on instantiation.
"""

import warnings


_DEPRECATION_MESSAGE = (
    "ProvenanceGraph is deprecated and will be removed. "
    "Use core.knowledge_graph.KnowledgeGraph or stores.graph_store.GraphStore instead."
)


def __getattr__(name):
    if name == "ProvenanceGraph":
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        from core.knowledge_graph import KnowledgeGraph

        class ProvenanceGraph(KnowledgeGraph):
            def __init__(self, path: str = "data/knowledge_graph.json", *args, **kwargs):
                warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
                super().__init__(path=path, *args, **kwargs)

        return ProvenanceGraph
    if name == "KnowledgeGraph":
        from core.knowledge_graph import KnowledgeGraph
        return KnowledgeGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
