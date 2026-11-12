import re

from core.contradiction import content_cosine_similarity
from core.memory_node import MemoryNode

_TRUSTED_STATUSES = frozenset({"verified", "user_asserted", "derived"})
_FLAGGED_STATUSES = frozenset({"planted", "contradicted"})


class AbstentionEngine:
    """Determines whether the system should abstain from answering based on memory trust and relevance."""

    @staticmethod
    def _extract_topic(query: str) -> str:
        topic = re.sub(r"^(?:what|where|when|who|why|how)\s+(?:is|are|was|were|do|does|did)\s+", "", query.strip(), flags=re.IGNORECASE)
        topic = topic.rstrip("?.! ").strip()
        return topic if topic else query.strip()

    def should_abstain(
        self,
        query: str,
        retrieved_nodes: list[MemoryNode],
        min_similarity: float = 0.6,
    ) -> tuple[bool, str]:
        """Return (True, reason) when retrieved memories lack trust or relevance; (False, '') otherwise."""
        topic = self._extract_topic(query)

        if not retrieved_nodes:
            return (
                True,
                f"I don't have verified information about {topic}. No relevant memories were retrieved.",
            )

        statuses = {node.trust_status for node in retrieved_nodes}

        if statuses <= _FLAGGED_STATUSES:
            if statuses == {"planted"}:
                return (
                    True,
                    f"I don't have verified information about {topic}. The closest memory is flagged as planted.",
                )
            if statuses == {"contradicted"}:
                return (
                    True,
                    f"I don't have verified information about {topic}. All retrieved memories are flagged as contradicted.",
                )
            return (
                True,
                f"I don't have verified information about {topic}. The retrieved memories are flagged as planted or contradicted.",
            )

        has_trusted = any(node.trust_status in _TRUSTED_STATUSES for node in retrieved_nodes)
        if not has_trusted:
            return (
                True,
                f"I don't have verified information about {topic}. No trusted memories were retrieved.",
            )

        if len(retrieved_nodes) == 1:
            similarity = content_cosine_similarity(query, retrieved_nodes[0].content)
            if similarity < min_similarity:
                return (
                    True,
                    f"I don't have verified information about {topic}. The closest memory has insufficient relevance (similarity {similarity:.2f} < {min_similarity:.2f}).",
                )

        return (False, "")

