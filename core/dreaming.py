"""Honcho-style dreaming and local reward gating for memory consolidation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


GATE_QUESTIONS = {
    "gate": {
        "type": "choice",
        "instructions": (
            "Should this candidate memory be accepted by the local dreaming gate, "
            "or escalated because it is unsafe, ambiguous, contradictory, overbroad, "
            "or unsupported by the supplied memory?"
        ),
        "criteria": {
            "accept": "Faithful, scoped, deletion-safe, and supported by the memory context.",
            "escalate": "Ambiguous, contradictory, unsafe, hallucinated, or not safely decidable locally.",
        },
    }
}

_STOPWORDS = {
    "a", "an", "and", "are", "be", "for", "from", "in", "is", "it", "of", "on", "or",
    "that", "the", "to", "use", "uses", "with", "will", "this", "user", "keep", "active",
}


def _evidence_support(context: Any, candidate: str) -> tuple[bool, str]:
    """Reject unsupported claims before trusting a learned gate."""
    source = json.dumps(context, ensure_ascii=False, default=str).lower()
    candidate_tokens = [t for t in re.findall(r"[\w-]+", candidate.lower()) if len(t) > 2 and t not in _STOPWORDS]
    if not candidate_tokens:
        return False, "empty_candidate_claims"
    supported = sum(1 for token in candidate_tokens if token in source)
    ratio = supported / len(candidate_tokens)
    deletion_terms = {"deleted", "deletion", "restore", "restored", "resurrect", "purge"}
    if deletion_terms.intersection(candidate.lower().split()) and not deletion_terms.intersection(source.split()):
        return False, "unsupported_deletion_claim"
    if ratio < 0.35:
        return False, f"insufficient_source_support:{ratio:.2f}"
    return True, f"source_support:{ratio:.2f}"


@dataclass
class DreamDecision:
    action: str
    confidence: float
    candidate: str
    reason: str
    laya_available: bool
    llm_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "candidate": self.candidate,
            "reason": self.reason,
            "laya_available": self.laya_available,
            "llm_used": self.llm_used,
            "metadata": self.metadata,
        }


def _probabilities(answer: Any) -> dict[str, float]:
    if not isinstance(answer, dict):
        return {}
    values = answer.get("probabilities") or answer.get("probs") or {}
    return {str(k): float(v) for k, v in values.items() if isinstance(v, (int, float))}


class DreamingGate:
    """Local Laya reward gate with an explicit escalation path.

    Laya is loaded lazily so normal MNEMOSYNE use remains lightweight when a
    trained gate checkpoint is not configured.
    """

    def __init__(self, model_dir: Optional[str] = None, threshold: Optional[float] = None):
        self.model_dir = model_dir or os.getenv("MNEMOSYNE_LAYA_GATE_MODEL", "outputs/laya-mnemosyne-gate")
        self.threshold = float(threshold or os.getenv("MNEMOSYNE_DREAMING_THRESHOLD", "0.75"))
        self._agent = None
        self.load_error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self._agent is not None

    def _load(self) -> None:
        if self._agent is not None or self.load_error is not None:
            return
        if not os.path.exists(self.model_dir):
            self.load_error = f"Laya gate checkpoint not found: {self.model_dir}"
            return
        try:
            import laya
            self._agent = laya.load(self.model_dir, device=os.getenv("MNEMOSYNE_LAYA_DEVICE", "cpu"))
        except Exception as exc:  # local gate failure must escalate, never silently accept
            self.load_error = str(exc)

    def decide(self, context: Any, candidate: str, metadata: Optional[dict[str, Any]] = None) -> DreamDecision:
        self._load()
        supported, support_reason = _evidence_support(context, candidate)
        if not supported:
            return DreamDecision("escalate", 0.0, candidate, support_reason,
                                 self._agent is not None, metadata=metadata or {})
        if self._agent is None:
            return DreamDecision(
                action="escalate",
                confidence=0.0,
                candidate=candidate,
                reason=self.load_error or "laya_gate_unavailable",
                laya_available=False,
                metadata=metadata or {},
            )
        state = json.dumps({"memory_context": context, "candidate": candidate, "metadata": metadata or {}},
                           ensure_ascii=False, sort_keys=True, default=str)
        try:
            result = self._agent.predict(state, GATE_QUESTIONS)
            answer = ((result or {}).get("answers") or {}).get("gate", {})
            probs = _probabilities(answer)
            choice = str(answer.get("choice", ""))
            confidence = float(probs.get(choice, 0.0))
            if choice == "accept" and confidence >= self.threshold:
                return DreamDecision("accept", confidence, candidate, "laya_accept", True, metadata=metadata or {})
            return DreamDecision("escalate", confidence, candidate, "laya_low_confidence_or_escalate", True, metadata=metadata or {})
        except Exception as exc:
            return DreamDecision("escalate", 0.0, candidate, f"laya_error:{exc}", True, metadata=metadata or {})


class HonchoDreaming:
    """Consolidate active session nodes, gate them locally, then escalate ambiguity."""

    def __init__(self, gate: Optional[DreamingGate] = None):
        self.gate = gate or DreamingGate()

    @staticmethod
    def candidate_from_nodes(nodes: Iterable[Any], token_budget: int = 256) -> str:
        lines: list[str] = []
        tokens = 0
        for node in nodes:
            if getattr(node, "deletion_state", "active") != "active":
                continue
            text = getattr(node, "summary_l1", "") or getattr(node, "content", "")
            cost = len(text.split())
            if tokens + cost > token_budget:
                continue
            lines.append(text)
            tokens += cost
        return "\n".join(lines)

    def consolidate(self, nodes: Iterable[Any], llm: Any = None, token_budget: int = 256) -> DreamDecision:
        nodes = list(nodes)
        context = [{"node_id": n.node_id, "content": n.content, "session_id": n.session_id,
                    "deletion_state": n.deletion_state} for n in nodes
                   if getattr(n, "deletion_state", "active") == "active"]
        candidate = self.candidate_from_nodes(nodes, token_budget=token_budget)
        decision = self.gate.decide(context, candidate, {"source_node_ids": [n.node_id for n in nodes]})
        if decision.action == "accept" or llm is None:
            return decision
        try:
            generated = llm.summarize(candidate)
            if isinstance(generated, dict):
                decision.candidate = generated.get("l2") or generated.get("l1") or candidate
                decision.action = "resolved_by_llm"
                decision.reason = "laya_escalated_to_llm"
                decision.llm_used = True
        except Exception as exc:
            decision.reason = f"llm_error:{exc}"
        return decision
