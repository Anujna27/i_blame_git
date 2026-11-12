from collections import Counter
import hashlib
import math
import re
from typing import Literal, Optional
import uuid

from dataclasses import dataclass, field

from core.memory_node import MemoryNode

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "could",
    "should", "can", "may", "might", "must", "shall", "in", "on", "at",
    "by", "for", "of", "to", "from", "with", "about", "as", "into",
    "what", "where", "when", "who", "whom", "which", "why", "how",
    "me", "my", "mine", "you", "your", "yours", "we", "our", "they",
    "their", "it", "its", "this", "that", "these", "those", "tell",
    "user", "users", "user's", "s", "not", "no", "never",
})

_NEGATION_TOKENS = frozenset({
    "not", "no", "never", "neither", "nor", "cannot", "cant",
})

_CONTRACTION_MAP = {
    "isn't": "is",
    "isnt": "is",
    "aren't": "are",
    "arent": "are",
    "wasn't": "was",
    "wasnt": "was",
    "weren't": "were",
    "werent": "were",
    "don't": "do",
    "dont": "do",
    "doesn't": "does",
    "doesnt": "does",
    "didn't": "did",
    "didnt": "did",
    "won't": "will",
    "wont": "will",
    "wouldn't": "would",
    "wouldnt": "would",
    "can't": "can",
    "cant": "can",
    "couldn't": "could",
    "couldnt": "could",
    "shouldn't": "should",
    "shouldnt": "should",
    "hasn't": "has",
    "hasnt": "has",
    "haven't": "have",
    "havent": "have",
    "hadn't": "had",
    "hadnt": "had",
}

_SENTENCE_MODEL = None
_SENTENCE_MODEL_CHECKED = False


def _get_sentence_model():
    """Lazily load sentence-transformers all-MiniLM-L6-v2 if installed and available locally."""
    global _SENTENCE_MODEL, _SENTENCE_MODEL_CHECKED
    if _SENTENCE_MODEL_CHECKED:
        return _SENTENCE_MODEL
    _SENTENCE_MODEL_CHECKED = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _SENTENCE_MODEL = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    except Exception:
        _SENTENCE_MODEL = None
    return _SENTENCE_MODEL


def _stem_token(token: str) -> str:
    """Apply lightweight suffix normalization for English tokens."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    return token


def _extract_content_tokens(text: str) -> list[str]:
    """Extract normalized non-stopword tokens from text."""
    raw = re.findall(r"[a-z0-9]+", text.lower())
    tokens = [_stem_token(t) for t in raw if t not in _STOPWORDS]
    return tokens if tokens else [_stem_token(t) for t in raw]


def cosine_similarity_vectors(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def embed_text(text: str, dim: int = 384) -> list[float]:
    """Generate a dense normalized embedding using all-MiniLM-L6-v2 or deterministic feature hashing."""
    model = _get_sentence_model()
    if model is not None:
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    vector = [0.0] * dim
    content_tokens = _extract_content_tokens(text)
    raw_tokens = re.findall(r"[a-z0-9]+", text.lower())

    def _add_feature(feature: str, weight: float) -> None:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vector[idx] += sign * weight

    for tok in content_tokens:
        _add_feature(f"tok:{tok}", 3.0)
        if len(tok) >= 3:
            for i in range(len(tok) - 2):
                _add_feature(f"3g:{tok[i:i+3]}", 1.0)

    for i in range(len(content_tokens) - 1):
        _add_feature(f"bi:{content_tokens[i]}_{content_tokens[i+1]}", 1.5)

    for tok in raw_tokens:
        _add_feature(f"raw:{tok}", 0.3)

    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0.0:
        vector = [x / norm for x in vector]
    return vector


def content_cosine_similarity(text_a: str, text_b: str) -> float:
    """Compute cosine similarity between two texts for retrieval/abstention relevance."""
    model = _get_sentence_model()
    if model is not None:
        vecs = model.encode([text_a, text_b], normalize_embeddings=True)
        return cosine_similarity_vectors(list(vecs[0]), list(vecs[1]))

    ca = Counter(_extract_content_tokens(text_a))
    cb = Counter(_extract_content_tokens(text_b))
    if not ca or not cb:
        return 0.0
    dot = sum(ca[k] * cb[k] for k in ca)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return float(dot / (na * nb)) if na and nb else 0.0


def _topic_vector_weights(text: str) -> dict[str, float]:
    """Build weighted topic terms normalizing away negation markers and numeric literals."""
    cleaned = text.lower()
    for contraction, base in _CONTRACTION_MAP.items():
        cleaned = re.sub(rf"\b{re.escape(contraction)}\b", base, cleaned)

    raw_tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", cleaned)
    weights: dict[str, float] = {}
    skip_aux = {"do", "does", "did"}
    for i, tok in enumerate(raw_tokens):
        if tok in _NEGATION_TOKENS:
            continue
        if tok in skip_aux and i + 1 < len(raw_tokens) and raw_tokens[i + 1] in _NEGATION_TOKENS:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            weights["<num>"] = weights.get("<num>", 0.0) + 0.25
        elif tok in _STOPWORDS:
            weights[tok] = weights.get(tok, 0.0) + 0.4
        else:
            stem = _stem_token(tok)
            weights[stem] = weights.get(stem, 0.0) + 1.0
    return weights


def topic_cosine_similarity(text_a: str, text_b: str) -> float:
    """Compute embedding or TF-IDF-style topic cosine similarity between two statements."""
    model = _get_sentence_model()
    if model is not None:
        vecs = model.encode([text_a, text_b], normalize_embeddings=True)
        return cosine_similarity_vectors(list(vecs[0]), list(vecs[1]))

    wa = _topic_vector_weights(text_a)
    wb = _topic_vector_weights(text_b)
    if not wa or not wb:
        return 0.0
    dot = sum(wa[k] * wb[k] for k in wa if k in wb)
    na = math.sqrt(sum(v * v for v in wa.values()))
    nb = math.sqrt(sum(v * v for v in wb.values()))
    return float(dot / (na * nb)) if na and nb else 0.0


@dataclass(kw_only=True)
class Conflict:
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_a_id: str
    node_b_id: str
    description: str
    resolution_status: Literal["unresolved", "resolved_a", "resolved_b", "needs_user_input"] = "unresolved"


class ContradictionEngine:
    """Detects and tracks semantic contradictions across MemoryNode instances."""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self._nodes: dict[str, MemoryNode] = {}

    @staticmethod
    def _extract_numbers(text: str) -> list[float]:
        return [float(m) for m in re.findall(r"\d+(?:\.\d+)?", text)]

    @staticmethod
    def _is_are_polarity(text: str) -> Optional[bool]:
        """Return False for negated is/are, True for positive is/are, or None if absent."""
        lower = text.lower()
        if re.search(
            r"\b(?:isn't|aren't|isnt|arent)\b|\b(?:is|are)\b(?:\s+\w+){0,2}\s+\b(?:not|never|no)\b",
            lower,
        ):
            return False
        if re.search(r"\b(?:is|are)\b", lower):
            return True
        return None

    def _has_semantic_negation(self, text_a: str, text_b: str) -> tuple[bool, str]:
        """Check whether two texts differ in numeric values or is/are polarity."""
        nums_a = self._extract_numbers(text_a)
        nums_b = self._extract_numbers(text_b)
        if nums_a and nums_b and nums_a != nums_b:
            return True, f"conflicting numeric values ({nums_a} vs {nums_b})"

        pol_a = self._is_are_polarity(text_a)
        pol_b = self._is_are_polarity(text_b)
        if pol_a is not None and pol_b is not None and pol_a != pol_b:
            return True, "opposite 'is/are' polarity"

        return False, ""

    @staticmethod
    def _verified_overrides(node_a: MemoryNode, node_b: MemoryNode) -> bool:
        """Verified ground truth supersedes non-verified claims without raising a conflict."""
        statuses = {node_a.trust_status, node_b.trust_status}
        return "verified" in statuses and len(statuses) > 1

    def register_nodes(self, nodes: list[MemoryNode]) -> None:
        """Register nodes so resolve() can update their trust_status and contradicts lists."""
        for node in nodes:
            self._nodes[node.node_id] = node

    def detect(self, new_node: MemoryNode, existing_nodes: list[MemoryNode]) -> list[Conflict]:
        """Detect contradictions between new_node and existing_nodes using similarity and negation checks."""
        self._nodes[new_node.node_id] = new_node
        conflicts: list[Conflict] = []

        for existing in existing_nodes:
            self._nodes[existing.node_id] = existing
            if existing.node_id == new_node.node_id:
                continue
            if existing.deletion_state != "active" or new_node.deletion_state != "active":
                continue
            if self._verified_overrides(new_node, existing):
                continue

            similarity = topic_cosine_similarity(new_node.content, existing.content)
            if similarity <= self.similarity_threshold:
                continue

            negated, reason = self._has_semantic_negation(new_node.content, existing.content)
            if not negated:
                continue

            conflicts.append(
                Conflict(
                    node_a_id=new_node.node_id,
                    node_b_id=existing.node_id,
                    description=(
                        f"Contradiction detected (similarity={similarity:.2f}, {reason}): "
                        f"'{new_node.content}' vs '{existing.content}'"
                    ),
                    resolution_status="unresolved",
                )
            )

        return conflicts

    def resolve(
        self,
        conflict: Conflict,
        resolution: str,
        node_a: Optional[MemoryNode] = None,
        node_b: Optional[MemoryNode] = None,
    ) -> None:
        """Mark both conflicting nodes as contradicted, link IDs, and update resolution_status."""
        valid_statuses = {"unresolved", "resolved_a", "resolved_b", "needs_user_input"}
        if resolution not in valid_statuses:
            raise ValueError(f"Invalid resolution '{resolution}'; expected one of {sorted(valid_statuses)}")

        a = node_a or self._nodes.get(conflict.node_a_id)
        b = node_b or self._nodes.get(conflict.node_b_id)

        if a is not None:
            a.trust_status = "contradicted"
            if conflict.node_b_id not in a.contradicts:
                a.contradicts.append(conflict.node_b_id)

        if b is not None:
            b.trust_status = "contradicted"
            if conflict.node_a_id not in b.contradicts:
                b.contradicts.append(conflict.node_a_id)

        conflict.resolution_status = resolution  # type: ignore[assignment]

