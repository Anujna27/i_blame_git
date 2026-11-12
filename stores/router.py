import re
import time
from typing import Any

from core.contradiction import _extract_content_tokens
from core.memory_node import MemoryNode

_ROUTE_MAP = {
    "preference": "graph",
    "temporal_fact": "graph",
    "document": "vector",
    "long_context": "vector",
    "task_context": "prompt",
    "short_term": "prompt",
    "procedure": "code",
    "workflow": "code",
}


class StorageRouter:
    """Deprecated compatibility helper; AgentA uses Graph + Vector directly.

    New application code should use ContextBuilder instead of routing knowledge
    to one of several unrelated stores.
    """

    def route(self, knowledge_type: str, content: str) -> str:
        """Return target store ('graph' | 'vector' | 'prompt' | 'code') for a knowledge_type."""
        normalized = (knowledge_type or "").strip().lower()
        return _ROUTE_MAP.get(normalized, "vector")

    @staticmethod
    def _match_nodes(query: str, nodes: list[Any]) -> list[Any]:
        tokens = set(_extract_content_tokens(query))
        if not tokens:
            return list(nodes)
        matched = []
        for node in nodes:
            text = node.content if hasattr(node, "content") else str(node)
            node_tokens = set(_extract_content_tokens(text))
            raw_words = set(re.findall(r"[a-z0-9]+", text.lower()))
            if tokens & (node_tokens | raw_words):
                matched.append(node)
        return matched

    def _query_store(self, store_name: str, store: Any, query: str) -> list[Any]:
        if store_name == "graph" or (hasattr(store, "get_all_active_nodes") and not hasattr(store, "query")):
            return self._match_nodes(query, store.get_all_active_nodes())
        if hasattr(store, "query"):
            return store.query(query)
        if isinstance(store, list):
            return self._match_nodes(query, store)
        if callable(store):
            return store(query)
        return []

    @staticmethod
    def _count_tokens(nodes: list[Any]) -> int:
        total = 0
        for node in nodes:
            text = node.content if isinstance(node, MemoryNode) or hasattr(node, "content") else str(node)
            total += len(text.split())
        return total

    def measure_performance(
        self,
        knowledge_type: str,
        queries: list[str],
        stores: dict[str, Any],
    ) -> dict[str, Any]:
        """Benchmark each store on the given queries and report avg_tokens and avg_latency_ms."""
        results: list[dict[str, Any]] = []
        preferred = self.route(knowledge_type, "")

        for store_name, store_obj in stores.items():
            if not queries:
                results.append({"store": store_name, "avg_tokens": 0, "avg_latency_ms": 0.0})
                continue

            total_tokens = 0
            total_latency_ms = 0.0

            for q in queries:
                t0 = time.perf_counter()
                retrieved = self._query_store(store_name, store_obj, q)
                t1 = time.perf_counter()
                total_latency_ms += (t1 - t0) * 1000.0
                total_tokens += self._count_tokens(retrieved)

            results.append(
                {
                    "store": store_name,
                    "avg_tokens": int(round(total_tokens / len(queries))),
                    "avg_latency_ms": round(total_latency_ms / len(queries), 4),
                }
            )

        if not results:
            best_store = preferred
        else:
            best_entry = min(
                results,
                key=lambda r: (
                    0 if r["avg_tokens"] > 0 else 1,
                    r["avg_latency_ms"],
                    0 if r["store"] == preferred else 1,
                ),
            )
            best_store = best_entry["store"]

        return {"best_store": best_store, "results": results}

