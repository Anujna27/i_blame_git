from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
import warnings

import networkx as nx

from core.knowledge_graph import KnowledgeGraph

# Audit operation strings (Exact names):
# "graph_orphan_detected"
# "graph_orphan_healed"
# "graph_orphan_quarantined"
# "graph_entities_merged" (not used in this version, registered for future use)


@dataclass
class OrphanRecord:
    node_id: str
    entity_type: str
    content_preview: str  # first 100 chars of content
    orphan_type: str  # one of: degree_zero, deleted_parent, invalid_target, orphaned_session, duplicate
    detected_reason: str  # human-readable


@dataclass
class HealingAction:
    node_id: str
    action: str  # one of: reconnected_ancestor, restored_derivation, removed_broken_edge, similarity_link, quarantined, skipped
    method: str  # "deterministic" | "vector_similarity" | "quarantine" | "skipped"
    target_node_id: Optional[str]
    relationship: Optional[str]
    confidence: float
    reason: str


@dataclass
class HealingReport:
    session_id: Optional[str]
    orphans_found: list[OrphanRecord]
    actions_taken: list[HealingAction]
    quarantined: list[str]
    healed_count: int
    skipped_count: int


@dataclass
class DuplicatePair:
    node_a_id: str
    node_b_id: str
    similarity: float
    content_a_preview: str  # first 100 chars
    content_b_preview: str
    entity_type: str
    detection_method: str  # "jaccard" | "vector_similarity"


class GraphHealer:
    def __init__(
        self,
        graph: KnowledgeGraph,
        vector_store: Any = None,
        audit_chain: Any = None,
        similarity_threshold: float = 0.82,
        high_confidence_threshold: float = 0.92,
        llm_suggester: Any = None,
    ):
        self.graph = graph
        self.vector_store = vector_store
        self.audit_chain = audit_chain
        self.similarity_threshold = similarity_threshold
        self.high_confidence_threshold = high_confidence_threshold
        self.llm_suggester = llm_suggester

    def find_orphans(self, session_id: Optional[str] = None) -> list[OrphanRecord]:
        """Detect all orphan types.

        If session_id is provided, only detect orphans among entities that belong to
        that session OR whose edges involve that session. Otherwise detect globally.
        Returns a list of OrphanRecord, one per orphan.
        """
        all_orphans: list[OrphanRecord] = []
        seen: set[str] = set()

        for detector in [
            self._detect_invalid_target,
            self._detect_deleted_parent,
            self._detect_orphaned_session,
            self._detect_degree_zero,
            self._detect_duplicates,
        ]:
            for orphan in detector():
                if orphan.node_id not in seen:
                    seen.add(orphan.node_id)
                    all_orphans.append(orphan)

        if session_id is None:
            return all_orphans

        filtered: list[OrphanRecord] = []
        for orphan in all_orphans:
            ent = self.graph.get_entity(orphan.node_id) or {}
            ent_sess = ent.get("session_id", "")
            if ent_sess == session_id:
                filtered.append(orphan)
                continue

            involves = False
            if self.graph.graph.has_node(orphan.node_id):
                for _, _, data in self.graph.graph.in_edges(orphan.node_id, data=True):
                    if data.get("source_session") == session_id:
                        involves = True
                        break
                if not involves:
                    for _, _, data in self.graph.graph.out_edges(orphan.node_id, data=True):
                        if data.get("source_session") == session_id:
                            involves = True
                            break
            if involves:
                filtered.append(orphan)

        return filtered

    def _detect_degree_zero(self) -> list[OrphanRecord]:
        """Nodes where graph.degree(node_id) == 0 AND deletion_state == 'active'. These are isolated entities."""
        orphans: list[OrphanRecord] = []
        for nid in self.graph.graph.nodes:
            data = self.graph.graph.nodes[nid]
            if data.get("deletion_state") == "active" and self.graph.graph.degree(nid) == 0:
                preview = str(data.get("content", ""))[:100]
                orphans.append(
                    OrphanRecord(
                        node_id=nid,
                        entity_type=str(data.get("entity_type", "unknown")),
                        content_preview=preview,
                        orphan_type="degree_zero",
                        detected_reason="Isolated active entity with degree zero",
                    )
                )
        return orphans

    def _detect_deleted_parent(self) -> list[OrphanRecord]:
        """Nodes whose ONLY incoming edge is from a node with deletion_state in {'source_removed','invalidated'} AND the node itself has deletion_state == 'active'. These are children of deleted parents that were not properly invalidated."""
        orphans: list[OrphanRecord] = []
        deleted_states = {"source_removed", "invalidated"}
        for nid in self.graph.graph.nodes:
            data = self.graph.graph.nodes[nid]
            if data.get("deletion_state") != "active":
                continue
            in_edges = list(self.graph.graph.in_edges(nid))
            if not in_edges:
                continue
            all_parents_deleted = all(
                self.graph.graph.nodes.get(parent_id, {}).get("deletion_state") in deleted_states
                for parent_id, _ in in_edges
            )
            if all_parents_deleted:
                preview = str(data.get("content", ""))[:100]
                orphans.append(
                    OrphanRecord(
                        node_id=nid,
                        entity_type=str(data.get("entity_type", "unknown")),
                        content_preview=preview,
                        orphan_type="deleted_parent",
                        detected_reason="Parent entity is deleted/invalidated",
                    )
                )
        return orphans

    def _detect_invalid_target(self) -> list[OrphanRecord]:
        """Nodes with edges pointing to a node_id that no longer exists in the graph."""
        orphans: list[OrphanRecord] = []
        seen: set[str] = set()
        for u, v in self.graph.graph.edges():
            u_data = self.graph.graph.nodes.get(u, {})
            if u_data.get("deletion_state") not in ("active", None):
                continue
            v_exists = self.graph.graph.has_node(v) and bool(self.graph.graph.nodes.get(v))
            if not v_exists and u not in seen:
                seen.add(u)
                preview = str(u_data.get("content", ""))[:100]
                orphans.append(
                    OrphanRecord(
                        node_id=u,
                        entity_type=str(u_data.get("entity_type", "unknown")),
                        content_preview=preview,
                        orphan_type="invalid_target",
                        detected_reason=f"Edge points to target '{v}' that does not exist in graph",
                    )
                )
        return orphans

    def _detect_orphaned_session(self) -> list[OrphanRecord]:
        """Nodes whose session_id is non-empty but no other node in the graph shares that session_id AND the node has no edges. These are entities from a session that vanished."""
        orphans: list[OrphanRecord] = []
        session_counts: dict[str, int] = {}
        for nid in self.graph.graph.nodes:
            data = self.graph.graph.nodes[nid]
            sess = data.get("session_id")
            if sess:
                session_counts[sess] = session_counts.get(sess, 0) + 1

        for nid in self.graph.graph.nodes:
            data = self.graph.graph.nodes[nid]
            sess = data.get("session_id")
            if (
                sess
                and session_counts.get(sess) == 1
                and self.graph.graph.degree(nid) == 0
                and data.get("deletion_state") == "active"
            ):
                preview = str(data.get("content", ""))[:100]
                orphans.append(
                    OrphanRecord(
                        node_id=nid,
                        entity_type=str(data.get("entity_type", "unknown")),
                        content_preview=preview,
                        orphan_type="orphaned_session",
                        detected_reason=f"Entity belongs to vanished session '{sess}' and has no edges",
                    )
                )
        return orphans

    def _detect_duplicates(self) -> list[OrphanRecord]:
        """DO NOT IMPLEMENT. Leave as a stub returning [] with a comment: 'Duplicate detection requires the vector store and is handled in the similarity stage.' This prevents silent merges."""
        return []

    def _jaccard_similarity(self, a: str, b: str) -> float:
        """Word-level Jaccard similarity. Split on whitespace, lowercase, strip punctuation.
        Return |intersection| / |union|. Return 0.0 if both empty, 1.0 if both empty AND identical.
        """
        import string

        clean_a = a.translate(str.maketrans("", "", string.punctuation)).lower().split()
        clean_b = b.translate(str.maketrans("", "", string.punctuation)).lower().split()
        if not clean_a and not clean_b:
            return 1.0 if a == b else 0.0
        set_a = set(clean_a)
        set_b = set(clean_b)
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    def find_duplicates(self, threshold: float = 0.95) -> list[DuplicatePair]:
        """Detect pairs of ACTIVE entities with highly similar content.
        Do NOT merge, do NOT modify, do NOT delete. Read-only.

        Algorithm:
        1. Get all active entities from self.graph.get_active_entities().
        2. For each unordered pair (a, b):
           a. Skip if either is quarantined, deleted, or invalidated.
           b. Compute similarity:
              - If self.vector_store is available AND both entities can be embedded,
                use cosine similarity (query vector_store with a's content, check if b appears in top-10).
              - Otherwise, use _jaccard_similarity(a.content, b.content).
           c. If similarity >= threshold, add a DuplicatePair.
        3. Return the list sorted by similarity descending.
        """
        active_entities = [
            e
            for e in self.graph.get_active_entities()
            if e.get("deletion_state") == "active"
        ]

        if len(active_entities) > 500:
            warnings.warn(
                "Active entities exceed 500; capping to 500 for duplicate detection.",
                UserWarning,
                stacklevel=2,
            )
            active_entities = active_entities[:500]

        duplicates: list[DuplicatePair] = []
        vs_query_cache: dict[str, dict[str, float]] = {}

        def _get_vs_scores(content: str) -> dict[str, float]:
            if self.vector_store is None:
                return {}
            if content in vs_query_cache:
                return vs_query_cache[content]
            try:
                results = self.vector_store.query(content, top_k=10)
            except Exception:
                results = []
            score_map: dict[str, float] = {}
            for res in results:
                nid = getattr(res, "node_id", None) if hasattr(res, "node_id") else (
                    res.get("node_id") if isinstance(res, dict) else None
                )
                score = getattr(res, "score", None) if hasattr(res, "score") else (
                    res.get("score") if isinstance(res, dict) else None
                )
                if nid is not None and score is not None:
                    score_map[str(nid)] = float(score)
            vs_query_cache[content] = score_map
            return score_map

        n = len(active_entities)
        for i in range(n):
            a = active_entities[i]
            a_id = str(a.get("node_id", ""))
            a_content = str(a.get("content", ""))

            a_vs_scores = _get_vs_scores(a_content) if self.vector_store is not None else {}

            for j in range(i + 1, n):
                b = active_entities[j]
                b_id = str(b.get("node_id", ""))
                b_content = str(b.get("content", ""))

                if a.get("deletion_state") != "active" or b.get("deletion_state") != "active":
                    continue

                matched = False
                if self.vector_store is not None:
                    score = a_vs_scores.get(b_id)
                    if score is not None and score >= threshold:
                        duplicates.append(
                            DuplicatePair(
                                node_a_id=a_id,
                                node_b_id=b_id,
                                similarity=score,
                                content_a_preview=a_content[:100],
                                content_b_preview=b_content[:100],
                                entity_type=str(a.get("entity_type") or b.get("entity_type") or "unknown"),
                                detection_method="vector_similarity",
                            )
                        )
                        matched = True

                if not matched:
                    jaccard_score = self._jaccard_similarity(a_content, b_content)
                    if jaccard_score >= threshold:
                        duplicates.append(
                            DuplicatePair(
                                node_a_id=a_id,
                                node_b_id=b_id,
                                similarity=jaccard_score,
                                content_a_preview=a_content[:100],
                                content_b_preview=b_content[:100],
                                entity_type=str(a.get("entity_type") or b.get("entity_type") or "unknown"),
                                detection_method="jaccard",
                            )
                        )

        duplicates.sort(key=lambda dp: dp.similarity, reverse=True)
        return duplicates

    def merge_duplicate(self, keep_node_id: str, remove_node_id: str, actor="system", reason="explicit_duplicate_merge"):
        """Explicitly merge one duplicate into another; never called implicitly."""
        keep = self.graph.get_entity(keep_node_id); remove = self.graph.get_entity(remove_node_id)
        if not keep or not remove or keep.get("deletion_state") != "active" or remove.get("deletion_state") != "active":
            raise ValueError("both entities must be active before an explicit merge")
        merged_properties = dict(remove.get("properties") or {}); merged_properties.update(keep.get("properties") or {})
        keep["properties"] = merged_properties
        self.graph.graph.nodes[keep_node_id]["properties"] = merged_properties
        for source, _, attrs in list(self.graph.graph.in_edges(remove_node_id, data=True)):
            if source != keep_node_id and source != keep_node_id:
                try: self.graph.add_relationship(source, keep_node_id, attrs.get("relationship", "RELATED_TO"), metadata={"merged_from": remove_node_id})
                except Exception: pass
        self.graph.graph.nodes[remove_node_id]["deletion_state"] = "merged"
        self.graph.graph.nodes[remove_node_id]["properties"] = {"merged_into": keep_node_id, "merge_reason": reason}
        self.graph.persist()
        self._audit("graph_entities_merged", remove_node_id, {"kept_entity": keep_node_id, "actor": actor, "reason": reason})
        if self.vector_store is not None and hasattr(self.vector_store, "remove"):
            self.vector_store.remove(remove_node_id)
        return {"kept_entity": keep_node_id, "merged_entity": remove_node_id, "reason": reason}

    def _deterministic_repair(self, orphan: OrphanRecord) -> Optional[HealingAction]:
        ent = self.graph.get_entity(orphan.node_id) or {}

        # 1. Broken edge to invalid target -> remove broken edge
        if orphan.orphan_type == "invalid_target":
            broken_target = None
            for _, v in list(self.graph.graph.out_edges(orphan.node_id)):
                v_exists = self.graph.graph.has_node(v) and bool(self.graph.graph.nodes.get(v))
                if not v_exists:
                    broken_target = v
                    self.graph.graph.remove_edge(orphan.node_id, v)
                    if self.graph.graph.has_node(v) and not self.graph.graph.nodes.get(v):
                        self.graph.graph.remove_node(v)
                    break
            if broken_target is not None:
                self.graph.persist()
                return HealingAction(
                    node_id=orphan.node_id,
                    action="removed_broken_edge",
                    method="deterministic",
                    target_node_id=broken_target,
                    relationship=None,
                    confidence=1.0,
                    reason=f"Removed broken edge to non-existent node '{broken_target}'",
                )

        # 2. derivation_edges pointing to active parent
        derivation_edges = (
            ent.get("derivation_edges")
            or ent.get("properties", {}).get("derivation_edges")
            or []
        )
        for edge in derivation_edges:
            target_p = None
            if isinstance(edge, dict):
                target_p = (
                    edge.get("parent_id")
                    or edge.get("source_id")
                    or edge.get("child_id")
                    or edge.get("node_id")
                )
            elif isinstance(edge, str):
                target_p = edge

            if target_p and target_p != orphan.node_id and self.graph.has_entity(target_p):
                p_ent = self.graph.get_entity(target_p)
                if p_ent and p_ent.get("deletion_state") == "active":
                    if self.graph.graph.has_edge(target_p, orphan.node_id):
                        return HealingAction(
                            node_id=orphan.node_id,
                            action="skipped",
                            method="skipped",
                            target_node_id=target_p,
                            relationship="DERIVED_FROM",
                            confidence=1.0,
                            reason="existing edge",
                        )
                    self.graph.add_relationship(
                        target_p,
                        orphan.node_id,
                        "DERIVED_FROM",
                        metadata={"healing_method": "deterministic", "actor": "graph_healer"},
                    )
                    return HealingAction(
                        node_id=orphan.node_id,
                        action="restored_derivation",
                        method="deterministic",
                        target_node_id=target_p,
                        relationship="DERIVED_FROM",
                        confidence=1.0,
                        reason=f"Restored derivation edge from parent '{target_p}'",
                    )

        # 3. deleted_parent with an active ancestor
        if orphan.orphan_type == "deleted_parent":
            in_parents = [u for u, _ in self.graph.graph.in_edges(orphan.node_id)]
            for p in in_parents:
                for ancestor in nx.ancestors(self.graph.graph, p):
                    anc_ent = self.graph.get_entity(ancestor)
                    if anc_ent and anc_ent.get("deletion_state") == "active":
                        if self.graph.graph.has_edge(ancestor, orphan.node_id):
                            return HealingAction(
                                node_id=orphan.node_id,
                                action="skipped",
                                method="skipped",
                                target_node_id=ancestor,
                                relationship="DERIVED_FROM",
                                confidence=1.0,
                                reason="existing edge",
                            )
                        self.graph.add_relationship(
                            ancestor,
                            orphan.node_id,
                            "DERIVED_FROM",
                            metadata={"healing_method": "deterministic", "actor": "graph_healer"},
                        )
                        return HealingAction(
                            node_id=orphan.node_id,
                            action="reconnected_ancestor",
                            method="deterministic",
                            target_node_id=ancestor,
                            relationship="DERIVED_FROM",
                            confidence=1.0,
                            reason=f"Reconnected to active ancestor '{ancestor}' of deleted parent '{p}'",
                        )

        return None

    def _similarity_repair(self, orphan: OrphanRecord) -> Optional[HealingAction]:
        if self.vector_store is None:
            return None

        ent = self.graph.get_entity(orphan.node_id) or {}
        query_text = (ent.get("content") or "")[:200]
        if not query_text.strip():
            query_text = ent.get("entity_type") or "unknown"

        try:
            results = self.vector_store.query(query_text, top_k=5)
        except Exception as e:
            warnings.warn(f"vector_store.query failed: {e}", UserWarning, stacklevel=2)
            return None

        if not results:
            return None

        scored_candidates: list[tuple[str, float]] = []
        for res in results:
            target_id = None
            if hasattr(res, "node_id"):
                target_id = getattr(res, "node_id")
            elif isinstance(res, dict) and "node_id" in res:
                target_id = res["node_id"]

            if not target_id or target_id == orphan.node_id:
                continue

            target_ent = self.graph.get_entity(target_id)
            if not target_ent or target_ent.get("deletion_state") in (
                "source_removed",
                "invalidated",
                "quarantined",
            ):
                continue

            score = None
            if hasattr(res, "score"):
                score = float(getattr(res, "score"))
            elif isinstance(res, dict) and "score" in res:
                score = float(res["score"])

            if score is None:
                score = self._jaccard_similarity(
                    ent.get("content", ""), target_ent.get("content", "")
                )

            scored_candidates.append((target_id, score))

        if not scored_candidates:
            return None

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_target, best_score = scored_candidates[0]

        if best_score < self.similarity_threshold:
            return None

        if self.graph.graph.has_edge(orphan.node_id, best_target) or self.graph.graph.has_edge(
            best_target, orphan.node_id
        ):
            return HealingAction(
                node_id=orphan.node_id,
                action="skipped",
                method="skipped",
                target_node_id=best_target,
                relationship=None,
                confidence=best_score,
                reason="existing edge",
            )

        meta = {
            "healing_method": "vector_similarity",
            "confidence": best_score,
            "actor": "graph_healer",
        }
        if best_score < self.high_confidence_threshold:
            meta["requires_review"] = True
            reason = "Linked via vector similarity (requires review)"
        else:
            reason = "Linked via high-confidence vector similarity"

        self.graph.add_relationship(orphan.node_id, best_target, "RELATED_TO", metadata=meta)
        return HealingAction(
            node_id=orphan.node_id,
            action="similarity_link",
            method="vector_similarity",
            target_node_id=best_target,
            relationship="RELATED_TO",
            confidence=best_score,
            reason=reason,
        )

    def _llm_repair(self, orphan: OrphanRecord) -> Optional[HealingAction]:
        """Use an injected LLM suggestion only when it returns a valid target."""
        if not self.llm_suggester:
            return None
        try:
            suggestion = self.llm_suggester(self.graph.get_entity(orphan.node_id) or {},
                                            self.graph.get_active_entities())
            target = suggestion.get("target_node_id") if isinstance(suggestion, dict) else None
            confidence = float(suggestion.get("confidence", 0.0)) if isinstance(suggestion, dict) else 0.0
            relationship = (suggestion.get("relationship", "RELATED_TO") if isinstance(suggestion, dict) else "RELATED_TO")
            if not target or target == orphan.node_id or confidence < self.similarity_threshold or not self.graph.has_entity(target):
                return None
            self.graph.add_relationship(orphan.node_id, target, relationship, metadata={"healing_method":"llm_suggestion", "confidence":confidence, "actor":"graph_healer"})
            return HealingAction(orphan.node_id, "similarity_link", "llm_suggestion", target, relationship, confidence, "Linked from injected LLM suggestion")
        except Exception as exc:
            warnings.warn(f"llm_suggester failed: {exc}", UserWarning, stacklevel=2)
            return None

    def _quarantine(self, orphan: OrphanRecord) -> HealingAction:
        ent = self.graph.get_entity(orphan.node_id) or {}
        if ent.get("deletion_state") == "quarantined":
            return HealingAction(
                node_id=orphan.node_id,
                action="skipped",
                method="skipped",
                target_node_id=None,
                relationship=None,
                confidence=1.0,
                reason="already quarantined",
            )

        if self.graph.graph.has_node(orphan.node_id):
            self.graph.graph.nodes[orphan.node_id]["deletion_state"] = "quarantined"
            if hasattr(self.graph, "nodes") and orphan.node_id in self.graph.nodes:
                node_obj = self.graph.nodes[orphan.node_id]
                if hasattr(node_obj, "transition"):
                    try:
                        node_obj.transition("quarantined", actor="graph_healer", reason="no safe relationship could be inferred")
                    except Exception:
                        setattr(node_obj, "deletion_state", "quarantined")
                elif hasattr(node_obj, "deletion_state"):
                    setattr(node_obj, "deletion_state", "quarantined")
            self.graph.persist()

        return HealingAction(
            node_id=orphan.node_id,
            action="quarantined",
            method="quarantine",
            target_node_id=None,
            relationship=None,
            confidence=1.0,
            reason="No safe relationship could be inferred",
        )

    def _audit(self, operation: str, node_id: str, details: dict) -> None:
        """If self.audit_chain is None, return silently (healer works without audit).

        Otherwise call self.audit_chain.append(operation, node_id, details).
        Wrap in try/except — if audit fails, do not crash the healer; print a warning.
        """
        if self.audit_chain is None:
            return
        try:
            self.audit_chain.append(operation, node_id, details)
        except Exception as e:
            warnings.warn(f"audit_chain.append failed: {e}", UserWarning, stacklevel=2)

    def heal_orphans(self, session_id: Optional[str] = None) -> HealingReport:
        """Full pipeline. Steps:

        1. orphans = find_orphans(session_id)
        2. For each orphan, try deterministic repair first (see _deterministic_repair)
        3. For unresolved orphans, try similarity repair if vector_store is available (see _similarity_repair)
        4. For still-unresolved orphans, quarantine (see _quarantine)
        5. Log every action via _audit()
        6. Return HealingReport
        """
        orphans = self.find_orphans(session_id)
        actions_taken: list[HealingAction] = []
        quarantined_ids: list[str] = []
        healed_count = 0
        skipped_count = 0

        # Step 1: Log detection
        for orphan in orphans:
            self._audit(
                "graph_orphan_detected",
                orphan.node_id,
                {
                    "orphan_type": orphan.orphan_type,
                    "method": "detection",
                    "confidence": 1.0,
                    "target_node_id": None,
                    "reason": orphan.detected_reason,
                    "actor": "graph_healer",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Step 2: Deterministic repair pass
        unresolved: list[OrphanRecord] = []
        for orphan in orphans:
            action = self._deterministic_repair(orphan)
            if action is not None:
                actions_taken.append(action)
            else:
                unresolved.append(orphan)

        # Step 3: Similarity repair pass for unresolved
        still_unresolved: list[OrphanRecord] = []
        for orphan in unresolved:
            # If the node got connected during a previous repair, skip repair
            if (
                self.graph.graph.has_node(orphan.node_id)
                and self.graph.graph.degree(orphan.node_id) > 0
                and orphan.orphan_type in ("degree_zero", "orphaned_session")
            ):
                continue

            action = None
            if self.llm_suggester is not None:
                action = self._llm_repair(orphan)
            if self.vector_store is not None:
                action = action or self._similarity_repair(orphan)

            if action is not None:
                actions_taken.append(action)
            else:
                still_unresolved.append(orphan)

        # Step 4: Quarantine still-unresolved
        for orphan in still_unresolved:
            # If the node got connected during a previous repair, skip quarantine
            if (
                self.graph.graph.has_node(orphan.node_id)
                and self.graph.graph.degree(orphan.node_id) > 0
                and orphan.orphan_type in ("degree_zero", "orphaned_session")
            ):
                continue

            action = self._quarantine(orphan)
            actions_taken.append(action)

        # Step 5: Tally and Audit
        for action in actions_taken:
            orphan_type = "unknown"
            for o in orphans:
                if o.node_id == action.node_id:
                    orphan_type = o.orphan_type
                    break

            if action.method == "quarantine":
                quarantined_ids.append(action.node_id)
                self._audit(
                    "graph_orphan_quarantined",
                    action.node_id,
                    {
                        "orphan_type": orphan_type,
                        "method": action.method,
                        "confidence": action.confidence,
                        "target_node_id": action.target_node_id,
                        "reason": action.reason,
                        "actor": "graph_healer",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            elif action.method in ("deterministic", "vector_similarity"):
                healed_count += 1
                self._audit(
                    "graph_orphan_healed",
                    action.node_id,
                    {
                        "orphan_type": orphan_type,
                        "method": action.method,
                        "confidence": action.confidence,
                        "target_node_id": action.target_node_id,
                        "reason": action.reason,
                        "actor": "graph_healer",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            elif action.method == "skipped":
                skipped_count += 1

        return HealingReport(
            session_id=session_id,
            orphans_found=orphans,
            actions_taken=actions_taken,
            quarantined=quarantined_ids,
            healed_count=healed_count,
            skipped_count=skipped_count,
        )
