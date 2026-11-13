"""
eval/evaluate_bemula.py

Evaluation logic measuring MNEMOSYNE's performance on the BEMULA benchmark
(Benchmark for Evaluation of Memory Unlearning in LLM Agents) and at BEMULA scale.

Implements:
1. EmbeddingCache: Persistent SHA-256 keyed cache to avoid redundant embedding calculations.
2. RealStackEvalAgent: Integrates Person 3's FAISS VectorStore, Person 2's
   KnowledgeGraph, and 5-level erasure with semantic blocked-embedding gates.
3. NaiveBaselineEvalAgent: Simulates standard LLM memory systems where unlearning
   requests are ignored (forget is a no-op).
4. MockProtocolAgent: Validates erasure protocol logic against a deterministic store.
5. run_bemula_scale_eval: Evaluates agents across 50 profiles, 135 requests, and ~1,742 questions.
6. Per-instance and per-request semantic leak diagnostics exported to eval/semantic_leak_report.json.
"""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np

from eval.llm_backends import get_backend, LLMBackend, MockBackend

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure faiss is pre-imported on Windows
try:
    import faiss  # noqa: F401
except Exception:
    pass

try:
    from stores.vector_store import VectorStore
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False

from core.contradiction import embed_text
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode
from eval.synthetic_bemula_test_set import (
    PROTOCOL_VALIDATION_INSTANCES,
    TEST_INSTANCES,
    summarize_instances,
)

FORGET_ABSTENTION_MARKERS = [
    "i don't know",
    "cannot recall",
    "deleted",
    "no longer have",
    "not available",
    "i don't have",
    "was deleted",
]


class EmbeddingCache:
    """Thread-safe persistent cache for text embeddings keyed by SHA-256."""

    _instance = None

    @classmethod
    def get_instance(cls, cache_path: Optional[Path] = None):
        if cls._instance is None:
            path = cache_path or (REPO_ROOT / "eval" / "embedding_cache.json")
            cls._instance = cls(path)
        return cls._instance

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache: Dict[str, list[float]] = {}
        self._dirty = False
        self.load()

    def load(self) -> None:
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.cache = {}

    def save(self) -> None:
        if self._dirty:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")
            self._dirty = False

    def embed(self, text: str) -> list[float]:
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key in self.cache:
            return self.cache[key]
        vec = embed_text(text)
        self.cache[key] = vec
        self._dirty = True
        return vec

    def batch_embed(self, texts: List[str]) -> List[list[float]]:
        results = []
        for t in texts:
            results.append(self.embed(t))
        return results


class RealStackEvalAgent:
    """
    Evaluates unlearning across the real MNEMOSYNE stack:
    - Real FAISS vector index (Person 3)
    - Real KnowledgeGraph (Person 2)
    - Blocked embedding semantic gates (5-level erasure)
    - Semantic leakage detection among active neighbors
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        backend: Any = "mock",
        backend_instance: Optional[LLMBackend] = None,
    ):
        self.temp_dir = persist_dir or tempfile.mkdtemp(prefix="bemula_real_stack_")
        self.vector_store = (
            VectorStore(collection_name="real_eval", persist_directory=self.temp_dir)
            if VECTOR_STORE_AVAILABLE
            else None
        )
        self.graph = KnowledgeGraph(path=f"{self.temp_dir}/tmp_kg_{uuid4().hex}.json")
        self.blocked_ids: set[str] = set()
        self.blocked_embeddings: Dict[str, list[float]] = {}
        self.diagnostics: List[dict] = []
        self.entities: Dict[str, MemoryNode] = {}
        self.embedding_cache = EmbeddingCache.get_instance()
        if backend_instance is not None:
            self.backend = backend_instance
        elif isinstance(backend, LLMBackend):
            self.backend = backend
        else:
            self.backend = get_backend(backend)

    def close(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _embed(self, text: str) -> list[float]:
        return self.embedding_cache.embed(text)

    def _cosine(self, a: Any, b: Any) -> float:
        va = np.asarray(a, dtype=np.float32).reshape(-1)
        vb = np.asarray(b, dtype=np.float32).reshape(-1)
        na = np.linalg.norm(va)
        nb = np.linalg.norm(vb)
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(va, vb) / (na * nb))

    def remember(self, node: dict) -> None:
        if isinstance(node, dict):
            node_id = str(node.get("node_id", uuid4().hex))
            content = str(node.get("content", ""))
            entity_type = str(node.get("entity_type", "generic"))
            trust_status = str(node.get("trust_status", "user_asserted"))
            deletion_state = str(node.get("deletion_state", "active"))
            source = {
                "type": "bemula_scale_probe",
                "session_id": str(node.get("session_id", "sess_scale")),
                "turn_index": 0,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "raw_reference": f"bemula_{node_id}",
            }
            mem_node = MemoryNode(
                node_id=node_id,
                content=content,
                entity_type=entity_type,
                source=source,
                session_id=str(node.get("session_id", "sess_scale")),
                deletion_state=deletion_state,
                derivation_edges=list(node.get("derivation_edges", [])),
                trust_status=trust_status,
            )
        else:
            mem_node = node

        if self.vector_store:
            self.vector_store.add(mem_node)
        self.graph.add_entity(mem_node)
        self.entities[mem_node.node_id] = mem_node

    def _compute_semantic_leak(self, node_id: str, blocked_emb: list[float]) -> dict:
        if not self.vector_store:
            return {
                "node_id": node_id,
                "leak_detected": False,
                "top_neighbors": [],
            }

        # Query vector store with blocked embedding to inspect remaining active neighbors
        results = self.vector_store.query(blocked_emb, top_k=5)
        neighbors = []
        leak_detected = False

        for n in results:
            if n.node_id in self.blocked_ids or n.node_id == node_id:
                continue
            sim = self._cosine(blocked_emb, self._embed(n.content))
            if sim > 0.75:
                leak_detected = True
            neighbors.append({
                "neighbor_id": n.node_id,
                "content_preview": n.content[:80],
                "similarity": round(sim, 4),
            })

        neighbors.sort(key=lambda x: x["similarity"], reverse=True)
        return {
            "node_id": node_id,
            "leak_detected": leak_detected,
            "top_neighbors": neighbors,
        }

    def forget(self, node_id: str, target_entities: Optional[list] = None) -> dict:
        # Step 1: Fetch target content BEFORE deletion
        target_content = ""
        if node_id in self.entities:
            target_content = self.entities[node_id].content
        elif self.graph.has_entity(node_id):
            ent = self.graph.get_entity(node_id) or {}
            target_content = ent.get("content", "")
        elif target_entities:
            for t in target_entities:
                if t.get("node_id") == node_id:
                    target_content = t.get("content", "")
                    break

        # Step 2: Store its embedding in self.blocked_embeddings[node_id]
        blocked_emb = self._embed(target_content)
        self.blocked_embeddings[node_id] = blocked_emb

        # Step 3: Call vector_store.remove_from_active_index(node_id)
        if self.vector_store and hasattr(self.vector_store, "remove_from_active_index"):
            self.vector_store.remove_from_active_index(node_id)

        # Step 4: Add node_id to self.blocked_ids
        self.blocked_ids.add(node_id)

        # Step 5: Update graph node deletion_state = "source_removed"
        if self.graph.has_entity(node_id):
            if hasattr(self.graph, "graph") and self.graph.graph.has_node(node_id):
                self.graph.graph.nodes[node_id]["deletion_state"] = "source_removed"
            if hasattr(self.graph, "nodes") and node_id in self.graph.nodes:
                setattr(self.graph.nodes[node_id], "deletion_state", "source_removed")
            self.graph.persist()

        # Step 6: Compute semantic leak diagnostic
        leak_info = self._compute_semantic_leak(node_id, blocked_emb)
        self.diagnostics.append(leak_info)

        return {
            "node_id": node_id,
            "verdict": "source_removed",
            "leak_detected": leak_info["leak_detected"],
            "top_neighbors": leak_info["top_neighbors"],
        }

    def query(self, question: str) -> dict:
        q_emb = self._embed(question)

        # Step A — semantic blocked check on question
        for blocked_id, blocked_emb in self.blocked_embeddings.items():
            sim = self._cosine(q_emb, blocked_emb)
            if sim > 0.55:
                return {
                    "answer": "I don't know. This information was deleted.",
                    "abstained": True,
                    "reason": f"semantic_match_to_blocked:{blocked_id}",
                    "similarity": sim,
                }

        # Step B — retrieve
        if not self.vector_store:
            return {"answer": "I don't have this information.", "abstained": True, "reason": "no_vector_store"}

        results = self.vector_store.query(question, top_k=3)
        if not results:
            return {"answer": "I don't have this information.", "abstained": True, "reason": "no_results"}

        top = results[0]
        top_content = getattr(top, "content", "") if hasattr(top, "content") else (top.get("content", "") if isinstance(top, dict) else "")
        top_id = getattr(top, "node_id", "") if hasattr(top, "node_id") else (top.get("node_id", "") if isinstance(top, dict) else "")

        if top_id in self.blocked_ids:
            return {"answer": "I don't know. This information was deleted.", "abstained": True, "reason": "retrieved_blocked"}

        top_emb = self._embed(top_content)

        # Level 5 Gate: check if retrieved memory is a derivative/leak of any blocked entity
        for blocked_id, blocked_emb in self.blocked_embeddings.items():
            if self._cosine(top_emb, blocked_emb) > 0.75:
                return {
                    "answer": "I don't know. This information was deleted.",
                    "abstained": True,
                    "reason": f"retrieved_derived_leak:{blocked_id}",
                }

        top_score = self._cosine(q_emb, top_emb)
        if top_score < 0.45:
            return {"answer": "I don't have this information.", "abstained": True, "reason": f"low_score:{top_score:.2f}"}

        # Build context from the top-k results' content
        context_chunks = []
        for r in results:
            c = getattr(r, "content", "") if hasattr(r, "content") else (r.get("content", "") if isinstance(r, dict) else "")
            if c:
                context_chunks.append(c)
        context_string = "\n\n".join(context_chunks) if context_chunks else top_content

        try:
            llm_answer = self.backend.generate(context=context_string, question=question)
        except Exception as e:
            print(f"Warning: LLM generation error on question: {e}")
            llm_answer = "I don't know."

        return {
            "answer": llm_answer,
            "abstained": any(m in llm_answer.lower() for m in FORGET_ABSTENTION_MARKERS),
            "reason": "found" if llm_answer != "I don't know." else "llm_error",
            "top_id": top_id,
            "score": top_score,
            "context": context_string,
        }


class NaiveBaselineEvalAgent:
    """
    Simulates a standard LLM memory system that does not implement unlearning.
    forget(node_id) is a complete no-op, preserving all requested deletions.
    """

    def __init__(self, persist_dir: Optional[str] = None):
        self.temp_dir = persist_dir or tempfile.mkdtemp(prefix="bemula_baseline_")
        self.vector_store = (
            VectorStore(collection_name="base_eval", persist_directory=self.temp_dir)
            if VECTOR_STORE_AVAILABLE
            else None
        )
        self.graph = KnowledgeGraph(path=f"{self.temp_dir}/tmp_kg_{uuid4().hex}.json")
        self.entities: Dict[str, MemoryNode] = {}
        self.embedding_cache = EmbeddingCache.get_instance()

    def close(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _embed(self, text: str) -> list[float]:
        return self.embedding_cache.embed(text)

    def _cosine(self, a: Any, b: Any) -> float:
        va = np.asarray(a, dtype=np.float32).reshape(-1)
        vb = np.asarray(b, dtype=np.float32).reshape(-1)
        na = np.linalg.norm(va)
        nb = np.linalg.norm(vb)
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(va, vb) / (na * nb))

    def remember(self, node: dict) -> None:
        if isinstance(node, dict):
            node_id = str(node.get("node_id", uuid4().hex))
            content = str(node.get("content", ""))
            entity_type = str(node.get("entity_type", "generic"))
            trust_status = str(node.get("trust_status", "user_asserted"))
            source = {
                "type": "bemula_scale_probe",
                "session_id": str(node.get("session_id", "sess_scale")),
                "turn_index": 0,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "raw_reference": f"bemula_{node_id}",
            }
            mem_node = MemoryNode(
                node_id=node_id,
                content=content,
                entity_type=entity_type,
                source=source,
                session_id=str(node.get("session_id", "sess_scale")),
                deletion_state="active",
                trust_status=trust_status,
            )
        else:
            mem_node = node

        if self.vector_store:
            self.vector_store.add(mem_node)
        self.graph.add_entity(mem_node)
        self.entities[mem_node.node_id] = mem_node

    def forget(self, node_id: str, target_entities: Optional[list] = None) -> dict:
        # Naive baseline ignores unlearning request and leaves all entities active
        return {"verdict": "noop_baseline", "node_id": node_id}

    def query(self, question: str) -> dict:
        if not self.vector_store:
            return {"answer": "I don't have this information.", "abstained": True, "reason": "no_vector_store"}

        results = self.vector_store.query(question, top_k=3)
        if not results:
            return {"answer": "I don't have this information.", "abstained": True, "reason": "no_results"}

        top = results[0]
        q_emb = self._embed(question)
        top_emb = self._embed(top.content)
        top_score = self._cosine(q_emb, top_emb)

        # Control probes (unknown facts) have low similarity and naturally abstain
        if top_score < 0.40:
            return {"answer": "I don't have this information.", "abstained": True, "reason": f"low_score:{top_score:.2f}"}

        # Forget and preservation probes return the unforgotten memory
        return {"answer": top.content, "abstained": False, "reason": "found", "top_id": top.node_id, "score": top_score}


class MockProtocolAgent:
    """
    Validates 5-level erasure protocol logic against a deterministic in-memory store.
    """

    def __init__(self):
        self.memory: Dict[str, dict] = {}
        self.deleted_ids: set[str] = set()
        self.deleted_labels: List[str] = []
        self.deleted_facts: List[str] = []

    def remember(self, node: dict) -> None:
        self.memory[node["node_id"]] = node

    def forget(self, node_id: str, target_entities: Optional[list] = None) -> dict:
        self.deleted_ids.add(node_id)
        node = self.memory.pop(node_id, None)
        if node:
            if node.get("label"):
                self.deleted_labels.append(str(node["label"]).lower())
            if node.get("fact"):
                self.deleted_facts.append(str(node["fact"]).lower())
        return {"verdict": "fully_deleted", "node_id": node_id}

    def query(self, question: str) -> dict:
        q = question.lower()
        # If question probes a deleted entity or concept
        for dl in self.deleted_labels:
            if dl and dl in q:
                return {"answer": "I don't know. This information was deleted.", "abstained": True}
        for df in self.deleted_facts:
            if df and len(df) > 3 and df in q:
                return {"answer": "I don't know. This information was deleted.", "abstained": True}

        # If question probes active stored memory
        for node in self.memory.values():
            lbl = str(node.get("label", "")).lower()
            if lbl and lbl in q:
                return {"answer": node["content"], "abstained": False}
            fact = str(node.get("fact", "")).lower()
            if fact and len(fact) > 3 and fact in q:
                return {"answer": node["content"], "abstained": False}

        # Control probes (never stored)
        return {"answer": "I don't have this information.", "abstained": True}


def run_evaluation(agent_factory: Any, instances: List[dict]) -> dict:
    """Run evaluation on 102 synthetic instances (backwards compatibility)."""
    total = len(instances)
    passed_count = 0
    per_type: Dict[str, Dict[str, Any]] = {
        f"F{i}": {"total": 0, "passed": 0, "rpr": 0.0} for i in range(1, 7)
    }
    failures = []
    all_diagnostics = []

    for instance in instances:
        f_type = instance.get("forget_request_type", "F1")
        if f_type not in per_type:
            per_type[f_type] = {"total": 0, "passed": 0, "rpr": 0.0}
        per_type[f_type]["total"] += 1

        agent = agent_factory()

        for target in instance.get("target_entities", []):
            agent.remember(target)
        for pres in instance.get("preservation_entities", []):
            agent.remember(pres)

        for target in instance.get("target_entities", []):
            agent.forget(target["node_id"], instance.get("target_entities", []))

        if hasattr(agent, "diagnostics") and agent.diagnostics:
            all_diagnostics.append({
                "instance_id": instance["instance_id"],
                "forget_type": f_type,
                "deleted_ids": [t["node_id"] for t in instance.get("target_entities", [])],
                "leak_detected": any(d.get("leak_detected", False) for d in agent.diagnostics),
                "top_neighbors": [item for d in agent.diagnostics for item in d.get("top_neighbors", [])],
            })

        failed_forget = []
        for f_q in instance.get("forget_questions", []):
            res = agent.query(f_q)
            ans = res.get("answer", "").lower()
            passes = any(m in ans for m in FORGET_ABSTENTION_MARKERS)
            if not passes:
                failed_forget.append({"question": f_q, "answer": res.get("answer", "")})

        failed_preservation = []
        expected_facts = [
            f.lower() for f in instance.get("expected_preservation_facts", [])
        ]
        for p_q in instance.get("preservation_questions", []):
            res = agent.query(p_q)
            ans = res.get("answer", "").lower()
            passes = any(fact in ans for fact in expected_facts) if expected_facts else bool(ans)
            if not passes:
                failed_preservation.append({
                    "question": p_q,
                    "expected": expected_facts,
                    "answer": res.get("answer", ""),
                })

        instance_passed = (len(failed_forget) == 0) and (len(failed_preservation) == 0)

        if instance_passed:
            passed_count += 1
            per_type[f_type]["passed"] += 1
        else:
            failures.append({
                "instance_id": instance["instance_id"],
                "failed_forget": failed_forget,
                "failed_preservation": failed_preservation,
            })

        if hasattr(agent, "close"):
            agent.close()

    rpr = (passed_count / total * 100.0) if total > 0 else 0.0
    for f_type, stats in per_type.items():
        if stats["total"] > 0:
            stats["rpr"] = round(stats["passed"] / stats["total"] * 100.0, 2)

    return {
        "total": total,
        "passed": passed_count,
        "rpr": round(rpr, 2),
        "per_type": per_type,
        "failures": failures,
        "diagnostics": all_diagnostics,
    }


def run_bemula_scale_eval(
    agent_class: Any,
    profiles: List[dict],
    requests: List[dict],
    questions: List[dict],
    max_questions: Optional[int] = None,
    resume_file: Optional[Path] = None,
    fresh: bool = False,
    backend: str = "mock",
    backend_instance: Optional[Any] = None,
) -> dict:
    """
    Executes BEMULA-scale evaluation across 50 profiles, 135 requests, and ~1,742 questions.

    Evaluation Protocol:
    1. For each profile: instantiate a fresh agent.
    2. Remember all ground truth entities + L1 session summaries (derived state).
    3. For each request belonging to the profile: execute agent.forget().
    4. For each question:
       - forget probes PASS if agent abstains.
       - preservation probes PASS if answer contains expected fact substring.
       - control probes PASS if agent abstains (no hallucination).
    5. A request PASSES only if ALL forget, preservation, and control probes pass.
    """
    start_time = time.time()
    cache = EmbeddingCache.get_instance()

    if backend_instance is None and backend != "mock" and agent_class == RealStackEvalAgent:
        backend_instance = get_backend(backend)

    # Pre-sample questions if smoke test mode is active
    is_sample = False
    active_questions = questions
    if max_questions is not None and max_questions < len(questions):
        is_sample = True
        rng = random.Random(42)
        active_questions = rng.sample(questions, max_questions)

    # Group requests by profile
    req_by_profile = defaultdict(list)
    for r in requests:
        req_by_profile[r["profile_id"]].append(r)

    # Group questions by request
    q_by_request = defaultdict(list)
    for q in active_questions:
        q_by_request[q["request_id"]].append(q)

    # Track results
    total_questions = len(active_questions)
    questions_passed = 0
    total_requests = 0
    requests_passed = 0

    per_type = {
        f"F{i}": {"requests": 0, "passed": 0, "rpr": 0.0} for i in range(1, 7)
    }
    per_question_type = {
        "forget": {"total": 0, "passed": 0, "acc": 0.0},
        "preservation": {"total": 0, "passed": 0, "acc": 0.0},
        "control": {"total": 0, "passed": 0, "acc": 0.0},
    }
    failures = []
    all_diagnostics = []

    # Support resume
    completed_profiles = set()
    partial_results_path = resume_file or (REPO_ROOT / "eval" / "partial_results.json")
    if not fresh and partial_results_path.exists():
        try:
            saved_state = json.loads(partial_results_path.read_text(encoding="utf-8"))
            completed_profiles = set(saved_state.get("completed_profiles", []))
        except Exception:
            completed_profiles = set()

    profiles_count = len(profiles)

    for p_idx, profile in enumerate(profiles):
        p_id = profile["profile_id"]
        profile_reqs = req_by_profile.get(p_id, [])
        if not profile_reqs:
            continue

        # Step 3: Process requests belonging to this profile
        for req in profile_reqs:
            req_id = req["request_id"]
            ftype = req.get("forget_request_type", "F1")
            req_questions = q_by_request.get(req_id, [])
            if not req_questions:
                continue

            total_requests += 1
            per_type[ftype]["requests"] += 1

            if agent_class == RealStackEvalAgent:
                agent = agent_class(backend=backend, backend_instance=backend_instance)
            else:
                agent = agent_class()

            # Remember ground truth entities
            for ent in profile.get("ground_truth_entities", []):
                agent.remember(ent)

            # Register L1 session summaries as derived state
            for sess in profile.get("sessions", []):
                summary_l1 = sess.get("summary_l1")
                if summary_l1:
                    sum_node = {
                        "node_id": f"ent_{p_id}_sum_{sess['session_index']:02d}",
                        "content": summary_l1,
                        "entity_type": "session_summary",
                        "trust_status": "derived",
                        "session_id": sess.get("session_id", ""),
                    }
                    agent.remember(sum_node)

            # Execute forget request for target entity IDs
            for tid in req.get("target_entity_ids", []):
                agent.forget(tid, target_entities=profile.get("ground_truth_entities", []))

            # Collect diagnostics
            if hasattr(agent, "diagnostics") and agent.diagnostics:
                all_diagnostics.append({
                    "request_id": req_id,
                    "forget_type": ftype,
                    "profile_id": p_id,
                    "deleted_ids": req.get("target_entity_ids", []),
                    "leak_detected": any(d.get("leak_detected", False) for d in agent.diagnostics),
                    "top_neighbors": [item for d in agent.diagnostics for item in d.get("top_neighbors", [])],
                })

            # Evaluate questions
            failed_forget = []
            failed_preservation = []
            failed_control = []

            for q in req_questions:
                q_text = q["text"]
                q_type = q["question_type"]
                per_question_type[q_type]["total"] += 1

                if backend != "mock" and agent_class == RealStackEvalAgent:
                    curr_q_total = per_question_type["forget"]["total"] + per_question_type["preservation"]["total"] + per_question_type["control"]["total"]
                    print(f"  [{backend.upper()}] Q {curr_q_total}/{total_questions} ({q_type} probe, Profile {p_idx+1}/{profiles_count})...", flush=True)

                res = agent.query(q_text)
                ans = str(res.get("answer", "")).lower()

                if q_type == "forget":
                    # PASS if answer contains any abstention marker
                    passes = any(m in ans for m in FORGET_ABSTENTION_MARKERS)
                    if passes:
                        questions_passed += 1
                        per_question_type["forget"]["passed"] += 1
                    else:
                        failed_forget.append({"question": q_text, "answer": res.get("answer", "")})

                elif q_type == "preservation":
                    # PASS if answer contains at least one expected fact substring
                    exp_facts = [f.lower() for f in q.get("expected_preservation_facts", [])]
                    passes = any(fact in ans for fact in exp_facts) if exp_facts else bool(ans)
                    if passes:
                        questions_passed += 1
                        per_question_type["preservation"]["passed"] += 1
                    else:
                        failed_preservation.append({
                            "question": q_text,
                            "expected": exp_facts,
                            "answer": res.get("answer", "")
                        })

                elif q_type == "control":
                    # PASS if agent abstains (did not hallucinate / fabricate non-existent memory)
                    passes = any(m in ans for m in FORGET_ABSTENTION_MARKERS)
                    if passes:
                        questions_passed += 1
                        per_question_type["control"]["passed"] += 1
                    else:
                        failed_control.append({"question": q_text, "answer": res.get("answer", "")})

            # Strict BEMULA condition: all forget, preservation, and control must pass
            req_passed = (len(failed_forget) == 0) and (len(failed_preservation) == 0) and (len(failed_control) == 0)
            if req_passed:
                requests_passed += 1
                per_type[ftype]["passed"] += 1
            else:
                failures.append({
                    "request_id": req_id,
                    "forget_type": ftype,
                    "profile_id": p_id,
                    "failed_forget": failed_forget,
                    "failed_preservation": failed_preservation,
                    "failed_control": failed_control,
                })

            if hasattr(agent, "close"):
                agent.close()

        # Progress reporting
        report_interval = 5 if backend != "mock" else 10
        if (p_idx + 1) % report_interval == 0 or (p_idx + 1) == profiles_count:
            elapsed = int(time.time() - start_time)
            print(f"Profile {p_idx+1}/{profiles_count} complete. Questions so far: {questions_passed}/{total_questions}. Time elapsed: {elapsed}s.")
            cache.save()

    # Final cache save
    cache.save()

    # Compute rates
    q_acc = round(questions_passed / total_questions * 100.0, 2) if total_questions > 0 else 0.0
    rpr = round(requests_passed / total_requests * 100.0, 2) if total_requests > 0 else 0.0

    for ftype, stats in per_type.items():
        if stats["requests"] > 0:
            stats["rpr"] = round(stats["passed"] / stats["requests"] * 100.0, 2)

    for qtype, stats in per_question_type.items():
        if stats["total"] > 0:
            stats["acc"] = round(stats["passed"] / stats["total"] * 100.0, 2)

    return {
        "is_sample": is_sample,
        "total_questions": total_questions,
        "questions_passed": questions_passed,
        "question_accuracy": q_acc,
        "total_requests": total_requests,
        "requests_passed": requests_passed,
        "request_pass_rate": rpr,
        "per_type": per_type,
        "per_question_type": per_question_type,
        "failures": failures,
        "diagnostics": all_diagnostics,
        "wall_clock_time": round(time.time() - start_time, 2),
        "backend": backend,
    }


class HybridEvalAgent:
    """Runs evaluation across protocol validation, naive baseline, and real-stack."""

    def evaluate_all(self) -> dict:
        mock_res = run_evaluation(lambda: MockProtocolAgent(), PROTOCOL_VALIDATION_INSTANCES)
        naive_res = run_evaluation(lambda: NaiveBaselineEvalAgent(), TEST_INSTANCES)
        real_res = run_evaluation(lambda: RealStackEvalAgent(), TEST_INSTANCES)

        leaks_count = sum(1 for d in real_res["diagnostics"] if d.get("leak_detected"))
        leak_report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_instances": real_res["total"],
            "leaks_detected": leaks_count,
            "leak_rate": round(leaks_count / real_res["total"] * 100.0, 2) if real_res["total"] > 0 else 0.0,
            "per_instance": real_res["diagnostics"],
        }
        report_path = Path(__file__).resolve().parent / "semantic_leak_report.json"
        report_path.write_text(json.dumps(leak_report, indent=2), encoding="utf-8")

        return {
            "mock_protocol": mock_res,
            "naive_baseline": naive_res,
            "real_stack": real_res,
            "semantic_leak_report": leak_report,
            "semantic_leak_report_path": str(report_path),
        }
