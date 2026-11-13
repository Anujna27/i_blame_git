import hashlib
import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

from .erasure_journal import ErasureJournal
from .residual_risk import ResidualRisk


@dataclass
class LevelResult:
    level_number: int
    level_name: str
    status: Literal["passed", "partial", "failed"]
    details: str
    evidence: dict


@dataclass
class ErasureReport:
    node_id: str
    node_content: str
    levels: list[LevelResult]
    verdict: Literal["fully_deleted", "partially_deleted", "failed"]
    residual_risks: list[ResidualRisk]
    timestamp: str
    signature: str
    entity_type: str = "memory"
    deleted_by: str = "user"
    reason: str = "user_requested_erasure"
    erased_entity_ids: list[str] = field(default_factory=list)
    context_id: Optional[str] = None
    content_digest: Optional[str] = None

    def to_dict(self):
        """Return an audit-safe report without plaintext deleted content."""
        data = asdict(self)
        data.update(
            {
                "entity_id": self.node_id,
                "entity_type": self.entity_type,
                "deleted_at": self.timestamp,
                "content_digest": self.content_digest
                or hashlib.sha256(self.node_content.encode("utf-8")).hexdigest(),
            }
        )
        data.pop("node_id", None)
        data.pop("node_content", None)
        return data


class ErasureEngine:
    """Coordinate scoped, auditable deletion across every memory projection.

    ``semantic_cleanup=False`` preserves the older conservative behaviour:
    semantically similar neighbours are reported as residual risk. The
    application path enables it, which additionally follows explicit entity
    references, exact secret fingerprints, supersession links, and derived
    descendants before removing the target from graph, vector, and filesystem
    projections.
    """

    _model = None
    _mutation_lock = threading.RLock()

    def __init__(
        self,
        blocked_set_path="data/blocked_inference.json",
        journal_path="data/erasure_journal.json",
    ):
        self.blocked_set_path = blocked_set_path
        self.blocked_ids = set()
        self.journal = ErasureJournal(journal_path)
        if os.path.exists(blocked_set_path):
            with open(blocked_set_path, encoding="utf-8") as f:
                self.blocked_ids = set(json.load(f))

    def _save_blocked_set(self):
        os.makedirs(os.path.dirname(self.blocked_set_path) or ".", exist_ok=True)
        with open(self.blocked_set_path, "w", encoding="utf-8") as f:
            json.dump(sorted(self.blocked_ids), f)

    @staticmethod
    def _similar(a, b):
        from collections import Counter

        ca, cb = Counter(a.lower().split()), Counter(b.lower().split())
        dot = sum(ca[k] * cb[k] for k in ca)
        na = sum(x * x for x in ca.values()) ** 0.5
        nb = sum(x * x for x in cb.values()) ** 0.5
        cosine = dot / (na * nb) if na and nb else 0.0
        security_overlap = (
            "key" in a.lower()
            and "key" in b.lower()
            and ("sk-" in a.lower() or "api key" in a.lower())
            and ("sk-" in b.lower() or "api key" in b.lower())
        )
        return max(cosine, 0.80 if security_overlap else 0.0)

    @staticmethod
    def _source(node) -> dict:
        source = getattr(node, "source", {}) or {}
        return dict(source) if isinstance(source, dict) else {}

    @classmethod
    def _properties(cls, node) -> dict:
        properties = getattr(node, "properties", {}) or {}
        return dict(properties) if isinstance(properties, dict) else {}

    @classmethod
    def _entity_refs(cls, node) -> set[str]:
        """Read stable application identity references, never session IDs."""
        props, source = cls._properties(node), cls._source(node)
        values = []
        for container in (props, source):
            for key in ("entity_refs", "entity_ref", "subject_ref", "entity_key"):
                value = container.get(key)
                if isinstance(value, (list, tuple, set)):
                    values.extend(value)
                elif value:
                    values.append(value)
        return {str(value) for value in values if str(value).strip()}

    @classmethod
    def _context_id(cls, node) -> Optional[str]:
        props, source = cls._properties(node), cls._source(node)
        for container in (props, source):
            for key in ("erasure_context_id", "context_id", "memory_context_id"):
                value = container.get(key)
                if value:
                    return str(value)
        return None

    @staticmethod
    def _normalise(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().casefold()

    @classmethod
    def _sensitive_tokens(cls, text: str) -> set[str]:
        """Extract deterministic high-entropy references without storing them."""
        tokens = set()
        patterns = (
            r"(?<!\w)[A-Za-z0-9][A-Za-z0-9_.+-]{5,}@[A-Za-z0-9.-]+(?!\w)",
            r"(?<!\w)sk-[A-Za-z0-9_-]{6,}(?!\w)",
            r"(?<!\w)[A-Z][A-Z0-9]{0,5}-[A-Z0-9_-]{6,}(?!\w)",
        )
        for pattern in patterns:
            tokens.update(match.casefold() for match in re.findall(pattern, text or ""))
        for raw in re.findall(r"(?<!\w)[A-Za-z0-9][A-Za-z0-9_.@:/-]{7,}(?!\w)", text or ""):
            if any(char.isalpha() for char in raw) and any(char.isdigit() for char in raw):
                tokens.add(raw.casefold())
        return tokens

    @classmethod
    def _candidate_text(cls, node) -> str:
        props = cls._properties(node)
        source = cls._source(node)
        values = [
            getattr(node, "content", ""),
            getattr(node, "summary_l0", ""),
            getattr(node, "summary_l1", ""),
            getattr(node, "content_l2", ""),
        ]
        for container in (props, source):
            for key in ("content", "text", "value", "document", "raw_reference"):
                if container.get(key):
                    values.append(str(container[key]))
        return " ".join(str(value) for value in values if value)

    @classmethod
    def _all_nodes(cls, graph_store) -> list:
        """Get a stable snapshot from KnowledgeGraph, GraphStore, or test doubles."""
        result, seen = [], set()

        def add(node):
            node_id = getattr(node, "node_id", None)
            if node is not None and node_id is not None and node_id not in seen:
                seen.add(node_id)
                result.append(node)

        active_fn = getattr(graph_store, "get_all_active_nodes", None)
        if callable(active_fn):
            try:
                for node in active_fn():
                    add(node)
            except Exception:
                pass

        graph = getattr(graph_store, "graph", None)
        if graph is not None and hasattr(graph, "nodes"):
            get_node = getattr(graph_store, "get_node", None)
            if callable(get_node):
                for node_id in list(graph.nodes):
                    try:
                        add(get_node(node_id))
                    except Exception:
                        pass

        nodes = getattr(graph_store, "nodes", None)
        if isinstance(nodes, dict):
            for node in nodes.values():
                add(node)

        return result

    @classmethod
    def _derived_ids(cls, graph_store, node_id: str) -> list[str]:
        fn = getattr(graph_store, "get_derived_descendants", None)
        if not callable(fn):
            fn = getattr(graph_store, "get_descendants", None)
        if not callable(fn):
            return []
        try:
            return [str(value) for value in fn(node_id)]
        except Exception:
            return []

    @classmethod
    def _edge_dependency_ids(cls, graph_store, root_ids: set[str]) -> set[str]:
        """Follow extraction/mention edges, but not generic RELATED_TO edges."""
        graph = getattr(graph_store, "graph", None)
        if graph is None or not hasattr(graph, "edges"):
            return set()
        dependencies = {"EXTRACTED_FROM", "MENTIONS"}
        found = set()
        for source, target, attrs in graph.edges(data=True):
            relation = str(attrs.get("relationship", attrs.get("type", ""))).upper()
            if relation not in dependencies:
                continue
            if source in root_ids:
                found.add(str(target))
            if target in root_ids:
                found.add(str(source))
        return found

    @classmethod
    def _collect_scope(
        cls,
        node,
        graph_store,
        semantic_cleanup: bool,
        context_id: Optional[str] = None,
        entity_refs: Optional[set[str]] = None,
    ) -> tuple[set[str], set[str]]:
        """Build an erasure manifest before any projection is mutated.

        A session is intentionally not treated as an identity boundary: two
        unrelated memories can share a session. Stable entity references,
        explicit context IDs, derivation/mention edges, supersession, and
        exact fingerprints are the boundaries that make scoped deletion safe.
        """
        root_id = str(node.node_id)
        refs = set(entity_refs or cls._entity_refs(node))
        scope_id = context_id or cls._context_id(node)
        root_text = cls._candidate_text(node)
        root_normalised = cls._normalise(getattr(node, "content", ""))
        fingerprints = cls._sensitive_tokens(root_text)
        all_nodes = cls._all_nodes(graph_store)
        manifest = {root_id}
        derived = set()
        queue = [root_id]

        while queue:
            parent_id = queue.pop(0)
            for child_id in cls._derived_ids(graph_store, parent_id):
                if child_id not in manifest:
                    manifest.add(child_id)
                    derived.add(child_id)
                    queue.append(child_id)

        changed = True
        while changed:
            changed = False
            for candidate in all_nodes:
                candidate_id = str(getattr(candidate, "node_id", ""))
                if not candidate_id or candidate_id in manifest:
                    continue
                candidate_refs = cls._entity_refs(candidate)
                candidate_context = cls._context_id(candidate)
                candidate_text = cls._candidate_text(candidate)
                candidate_normalised = cls._normalise(getattr(candidate, "content", ""))
                supersedes = str(getattr(candidate, "supersedes", "") or "")

                same_reference = bool(refs and refs.intersection(candidate_refs))
                same_scope = bool(scope_id and candidate_context == scope_id)
                exact_copy = bool(root_normalised and candidate_normalised == root_normalised)
                exact_fingerprint = bool(
                    fingerprints and fingerprints.intersection(cls._sensitive_tokens(candidate_text))
                )
                explicit_link = supersedes in manifest or candidate_id in cls._edge_dependency_ids(graph_store, manifest)
                if semantic_cleanup and (same_reference or same_scope or exact_copy or exact_fingerprint or explicit_link):
                    manifest.add(candidate_id)
                    changed = True
                    for child_id in cls._derived_ids(graph_store, candidate_id):
                        if child_id not in manifest:
                            manifest.add(child_id)
                            derived.add(child_id)
                            queue.append(child_id)
            while queue:
                parent_id = queue.pop(0)
                for child_id in cls._derived_ids(graph_store, parent_id):
                    if child_id not in manifest:
                        manifest.add(child_id)
                        derived.add(child_id)
                        queue.append(child_id)

        return manifest, derived

    @staticmethod
    def _scrub_node(node, state: str, deleted_by: str, reason: str) -> None:
        if node is None:
            return
        if getattr(node, "deletion_state", "active") == "active":
            node.transition(state, deleted_by, reason)
        elif state == "invalidated" and getattr(node, "deletion_state", "active") != "invalidated":
            node.transition("invalidated", deleted_by, reason)
        node.content = ""
        node.summary_l0 = ""
        node.summary_l1 = ""
        node.content_l2 = ""
        node.properties = {}
        node.derivation_edges = []
        node.contradicts = []
        node.supersedes = None
        node.is_blocked = True

    @staticmethod
    def _remove_vectors(vector_store, ids: set[str]) -> None:
        remove_many = getattr(vector_store, "remove_many", None)
        if callable(remove_many):
            remove_many(ids)
            return
        remove = getattr(vector_store, "remove", None)
        for node_id in ids:
            if callable(remove):
                remove(node_id)
            else:
                vector_store.remove_from_active_index(node_id)

    @staticmethod
    def _remove_graph_edges(graph_store, ids: set[str]) -> None:
        remove_edges = getattr(graph_store, "remove_entity_edges", None)
        if callable(remove_edges):
            for node_id in ids:
                try:
                    remove_edges(node_id, persist=False)
                except TypeError:
                    remove_edges(node_id)
            return
        graph = getattr(graph_store, "graph", None)
        if graph is not None and hasattr(graph, "remove_edges_from"):
            edges = []
            for node_id in ids:
                edges.extend(list(graph.in_edges(node_id)))
                edges.extend(list(graph.out_edges(node_id)))
            graph.remove_edges_from(set(edges))

    def delete(
        self,
        node_id,
        vector_store,
        graph_store,
        hash_chain,
        reason="user_requested_erasure",
        deleted_by="user",
        filesystem_store=None,
        semantic_cleanup=False,
        context_id: Optional[str] = None,
        entity_refs: Optional[list[str] | set[str]] = None,
    ):
        """Serialize deletion mutations within a process."""
        with self._mutation_lock:
            operation_id = self.journal.begin(node_id, deleted_by, reason)
            try:
                self.journal.advance(operation_id, "mutating")
                report = self._delete_unlocked(
                    node_id,
                    vector_store,
                    graph_store,
                    hash_chain,
                    reason,
                    deleted_by,
                    filesystem_store,
                    semantic_cleanup,
                    context_id,
                    set(entity_refs or []),
                )
                self.journal.complete(operation_id, report.verdict)
                return report
            except Exception as error:
                self.journal.advance(operation_id, "failed", {"error": str(error)})
                raise

    def _delete_unlocked(
        self,
        node_id,
        vector_store,
        graph_store,
        hash_chain,
        reason="user_requested_erasure",
        deleted_by="user",
        filesystem_store=None,
        semantic_cleanup=False,
        context_id: Optional[str] = None,
        entity_refs: Optional[set[str]] = None,
    ):
        node = graph_store.get_node(node_id)
        levels = []
        timestamp = datetime.now(timezone.utc).isoformat()
        entity_type = getattr(node, "entity_type", "memory") if node else "memory"
        original_content = getattr(node, "content", "") if node else ""
        content_digest = hashlib.sha256(original_content.encode("utf-8")).hexdigest() if node else None

        if node is not None and node.deletion_state != "active":
            details = {"state": node.deletion_state, "actor": deleted_by, "reason": reason}
            # A previous attempt can fail after graph scrubbing but before
            # vector/filesystem cleanup. Reconcile every already-blocked ID so
            # a retry actually finishes the operation instead of returning a
            # misleading idempotency no-op.
            recovery_ids = set(self.blocked_ids) | {str(node_id)}
            recovered_vectors = set()
            get_by_id = getattr(vector_store, "get_by_id", None)
            if callable(get_by_id):
                recovered_vectors = {
                    erased_id
                    for erased_id in recovery_ids
                    if get_by_id(erased_id) is not None
                }
                if recovered_vectors:
                    self._remove_vectors(vector_store, recovered_vectors)
            self._remove_graph_edges(graph_store, recovery_ids)
            if filesystem_store is not None and hasattr(filesystem_store, "delete_entity"):
                for erased_id in recovery_ids:
                    filesystem_store.delete_entity(erased_id)
            persist = getattr(graph_store, "persist", None) or getattr(graph_store, "save", None)
            if callable(persist):
                try:
                    persist()
                except Exception:
                    pass
            details["recovered_projection_ids"] = sorted(recovered_vectors)
            hash_chain.append("deletion_repeated", node_id, details, actor=deleted_by, reason=reason)
            levels = [
                LevelResult(
                    1,
                    "Source Record Removed",
                    "failed",
                    "Entity was already deleted; operation is idempotent.",
                    details,
                )
            ]
            for number, name in [
                (2, "Derived Artifacts Invalidated"),
                (3, "Inference Blocked"),
                (4, "Non-Inferability Checked"),
                (5, "State Restoration Checked"),
            ]:
                levels.append(LevelResult(number, name, "passed", "No additional mutation performed.", {}))
            payload = {"node_id": node_id, "verdict": "failed", "timestamp": timestamp, "repeat": True}
            signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            return ErasureReport(node_id, "", levels, "failed", [], timestamp, signature, entity_type, deleted_by, reason)

        if node is None:
            levels.append(
                LevelResult(
                    1,
                    "Source Record Removed",
                    "failed",
                    "Source entity was not found.",
                    {"vector_store_cleared": False, "graph_deletion_state": None},
                )
            )
            for number, name in [
                (2, "Derived Artifacts Invalidated"),
                (3, "Inference Blocked"),
                (4, "Non-Inferability Checked"),
                (5, "State Restoration Checked"),
            ]:
                levels.append(LevelResult(number, name, "passed", "No source entity was available.", {}))
            payload = {"node_id": node_id, "verdict": "failed", "timestamp": timestamp, "missing": True}
            signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            return ErasureReport(node_id, "", levels, "failed", [], timestamp, signature, entity_type, deleted_by, reason)

        manifest, derived = self._collect_scope(
            node,
            graph_store,
            semantic_cleanup,
            context_id=context_id,
            entity_refs=entity_refs or None,
        )
        descendants = sorted(derived)

        # Query before mutation so residual-risk analysis sees the original
        # active index. The manifest itself is excluded from risk reporting.
        candidates = []
        try:
            candidates = list(vector_store.query(original_content, top_k=3))
        except Exception:
            candidates = []
        try:
            graph_candidates = graph_store.get_all_active_nodes()[:50]
            seen_ids = {getattr(candidate, "node_id", None) for candidate in candidates}
            candidates.extend(candidate for candidate in graph_candidates if candidate.node_id not in seen_ids)
        except Exception:
            pass

        self._scrub_node(node, "source_removed", deleted_by, reason)
        hash_chain.append(
            "delete_level_1",
            node_id,
            {
                "action": "source_removed",
                "actor": deleted_by,
                "reason": reason,
                "timestamp": timestamp,
            },
            actor="agent",
            reason="erasure_request",
        )
        levels.append(
            LevelResult(
                1,
                "Source Record Removed",
                "passed",
                "Source record removed from active store and index.",
                {"vector_store_cleared": True, "graph_deletion_state": "source_removed"},
            )
        )

        invalidated, failed = [], []
        for dependent_id in sorted(manifest - {node_id}):
            child = graph_store.get_node(dependent_id)
            if child is None:
                failed.append(dependent_id)
                continue
            self._scrub_node(child, "invalidated", deleted_by, f"within erased entity scope: {reason}")
            invalidated.append(dependent_id)

        hash_chain.append(
            "delete_level_2",
            node_id,
            {
                "invalidated": invalidated,
                "failed": failed,
                "derived_count": len(descendants),
                "scoped_dependents": len(invalidated) - len(descendants),
            },
            actor="agent",
            reason="erasure_request",
        )
        level2_status = "passed" if not failed else ("partial" if invalidated else "failed")
        levels.append(
            LevelResult(
                2,
                "Derived Artifacts Invalidated",
                level2_status,
                f"Invalidated {len(invalidated)} of {len(manifest) - 1} scoped dependent artifacts.",
                {
                    "total_descendants": len(descendants),
                    "invalidated_children": invalidated,
                    "failed_children": failed,
                    "erased_entity_ids": sorted(manifest),
                },
            )
        )

        self.blocked_ids.update(manifest)
        self._save_blocked_set()
        hash_chain.append(
            "delete_level_3",
            node_id,
            {"blocked_set_size": len(self.blocked_ids), "blocked_entity_count": len(manifest)},
            actor="agent",
            reason="erasure_request",
        )
        levels.append(
            LevelResult(
                3,
                "Inference Blocked",
                "passed",
                "All erased entity IDs were added to the persistent inference block list.",
                {"blocked_set_size": len(self.blocked_ids), "blocked_entity_ids": sorted(manifest)},
            )
        )

        risks = []
        semantic_invalidated = []
        sensitive_tokens = self._sensitive_tokens(original_content)
        for candidate in candidates:
            candidate_id = getattr(candidate, "node_id", None)
            if not candidate_id or candidate_id in manifest:
                continue
            sim = self._similar(original_content, getattr(candidate, "content", ""))
            if sim <= 0.75:
                continue
            candidate_tokens = self._sensitive_tokens(getattr(candidate, "content", ""))
            exact_sensitive_overlap = bool(sensitive_tokens.intersection(candidate_tokens))
            if semantic_cleanup and exact_sensitive_overlap:
                canonical = graph_store.get_node(candidate_id) or candidate
                self._scrub_node(canonical, "invalidated", deleted_by, f"exact content match within erased scope: {reason}")
                manifest.add(candidate_id)
                semantic_invalidated.append(candidate_id)
            elif semantic_cleanup:
                # Scoped deletion is identity/fingerprint based. A merely
                # similar but independently referenced neighbour is not a
                # deletion target and should not manufacture a residual-risk
                # failure for every normal semantic neighbour.
                continue
            else:
                description = (
                    f"Deleted content may be partially reconstructable from {candidate_id} "
                    f"(similarity {sim:.2f}; sensitive-key overlap={exact_sensitive_overlap})."
                )
                risks.append(
                    ResidualRisk(
                        risk_type="semantic_neighbor_proximity",
                        cluster=candidate_id,
                        description=description,
                        severity="high" if sim > 0.85 else "medium",
                        affected_node_ids=[candidate_id],
                    )
                )

        if semantic_invalidated:
            self.blocked_ids.update(semantic_invalidated)
            self._save_blocked_set()

        hash_chain.append(
            "delete_level_4",
            node_id,
            {"risks_found": len(risks), "late_invalidated": semantic_invalidated},
            actor="agent",
            reason="erasure_request",
        )
        levels.append(
            LevelResult(
                4,
                "Non-Inferability Checked",
                "partial" if risks else "passed",
                "No unresolved semantic neighbors above threshold."
                if not risks
                else f"{len(risks)} semantic neighbor(s) may partially reconstruct the deleted content.",
                {
                    "neighbors_checked": len(candidates),
                    "risks_found": len(risks),
                    "risks": [asdict(risk) for risk in risks],
                    "semantic_invalidated": semantic_invalidated,
                },
            )
        )

        state_restoration_failed = bool(failed) or (bool(descendants) and not semantic_cleanup)
        st5 = "failed" if state_restoration_failed else "passed"
        detail5 = (
            f"{len(failed)} scoped artifacts could not be reached."
            if failed
            else (
                f"{len(manifest) - 1} dependent artifacts were scrubbed and their vectors/filesystem copies removed."
                if semantic_cleanup
                else (
                    f"{len(descendants)} derived artifacts were generated from the deleted content and cannot be "
                    "deterministically reversed. Return to 'never-written' state is not guaranteed."
                    if descendants
                    else "No derived artifacts were generated; state restoration is possible."
                )
            )
        )
        hash_chain.append(
            "delete_level_5",
            node_id,
            {"non_reversible_artifacts": [] if semantic_cleanup else descendants},
            actor="agent",
            reason="erasure_request",
        )
        levels.append(
            LevelResult(
                5,
                "State Restoration Checked",
                st5,
                detail5,
                {"non_reversible_artifacts": [] if semantic_cleanup else descendants},
            )
        )

        all_erased_ids = set(manifest) | set(semantic_invalidated)
        self._remove_vectors(vector_store, all_erased_ids)
        self._remove_graph_edges(graph_store, all_erased_ids)
        if filesystem_store is not None and hasattr(filesystem_store, "delete_entity"):
            for erased_id in all_erased_ids:
                filesystem_store.delete_entity(erased_id)

        persistence_error = None
        persist = getattr(graph_store, "persist", None) or getattr(graph_store, "save", None)
        if callable(persist):
            try:
                persist()
            except Exception as error:
                persistence_error = str(error)
        if persistence_error:
            levels[0].status = "partial"
            levels[0].details += f" Graph persistence failed: {persistence_error}"
            hash_chain.append(
                "deletion_persistence_failed",
                node_id,
                {"error": persistence_error},
                actor="agent",
                reason="erasure_request",
            )
            st5 = "failed"

        unresolved = []
        for erased_id in all_erased_ids:
            current = graph_store.get_node(erased_id)
            if current is not None and getattr(current, "deletion_state", "active") == "active":
                unresolved.append(erased_id)
            if callable(getattr(vector_store, "get_by_id", None)) and vector_store.get_by_id(erased_id) is not None:
                unresolved.append(erased_id)
        if unresolved:
            st5 = "failed"
            levels[4].status = "failed"
            levels[4].details += f" Unresolved projections: {len(set(unresolved))}."

        verdict = "failed" if levels[0].status == "failed" or level2_status == "failed" else (
            "partially_deleted" if st5 == "failed" or risks else "fully_deleted"
        )
        report_payload = {
            "node_id": node_id,
            "content_digest": content_digest,
            "erased_entity_ids": sorted(all_erased_ids),
            "levels": [asdict(level) for level in levels],
            "verdict": verdict,
            "residual_risks": [asdict(risk) for risk in risks],
            "timestamp": timestamp,
        }
        signature = hashlib.sha256(json.dumps(report_payload, sort_keys=True, default=str).encode()).hexdigest()
        report = ErasureReport(
            node_id=node_id,
            node_content=original_content,
            levels=levels,
            verdict=verdict,
            residual_risks=risks,
            timestamp=timestamp,
            signature=signature,
            entity_type=entity_type,
            deleted_by=deleted_by,
            reason=reason,
            erased_entity_ids=sorted(all_erased_ids),
            context_id=context_id or self._context_id(node),
            content_digest=content_digest,
        )
        hash_chain.append(
            "deletion_completed",
            node_id,
            {
                "verdict": verdict,
                "signature": signature,
                "actor": deleted_by,
                "reason": reason,
                "content_digest": content_digest,
                "erased_entity_ids": sorted(all_erased_ids),
                "content_redacted": True,
            },
            actor="agent",
            reason="erasure_request",
        )
        return report
