#!/usr/bin/env python3
"""
BEMULA-R: rigorous, adversarial real-stack unlearning evaluation.

Design rules
  * Ground truth is declared per node (forget / preserve) BEFORE deletion; never inferred from the engine.
  * Every leak check is content-based (unique canaries / subject-anchored regexes), never ID-only.
  * Every probe is validated pre-deletion (a probe that cannot find the target proves nothing).
  * A check the stack cannot support is "unsupported" and FAILS by default (no silent passes).
  * The harness is itself tested: sabotaged ("mutant") engines must be caught.
Usage: python bemula_rigorous.py [--per-type 17] [--background 300] [--seed 1337] [--top-k 25]
Exit code is 1 if any instance or scenario fails.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import random
import re
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.erasure_engine import ErasureEngine
from core.hash_chain import HashChain
from core.knowledge_graph import KnowledgeGraph
from core.memory_node import MemoryNode
from stores.filesystem_memory import FilesystemMemory
from stores.vector_store import VectorStore

F1, F2, F3, F4, F5, F6 = ("F1 (Factual)", "F2 (Compositional)", "F3 (Semantic Category)",
                          "F4 (Inferential)", "F5 (Temporal)", "F6 (Replacement)")
TYPES = [F1, F2, F3, F4, F5, F6]
ADVISORY = {"dangling_edges"}  # reported, never fails an instance
LEAK_CHECKS = {"target_scrubbed", "target_vec_gone", "no_content_leak", "probes_clean", "deps_forgotten", "disk_clean"}


class Unsupported(Exception):
    pass


# ----------------------------------------------------------------------------- adapters
def norm(s: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s))).casefold()


def is_active(n: Any) -> bool:
    return n is not None and getattr(n, "deletion_state", "active") == "active"


def dump(n: Any) -> str:
    """Every attribute of a node, normalised: catches leaks in metadata, not only .content."""
    try:
        return norm(json.dumps(vars(n), default=str))
    except TypeError:
        return norm(repr(n))


def text_of(o: Any) -> str:
    if o is None:
        return ""
    if isinstance(o, dict):
        return " ".join(str(o[k]) for k in ("content", "text", "document", "page_content") if k in o)
    return " ".join(str(getattr(o, k)) for k in ("content", "text", "document", "page_content") if isinstance(getattr(o, k, None), str))


def hit_id(h: Any) -> Optional[str]:
    if isinstance(h, (tuple, list)):
        return hit_id(h[0]) if h else None
    if isinstance(h, str):
        return h
    if isinstance(h, dict):
        for k in ("id", "node_id"):
            if k in h:
                return h[k]
        return hit_id(h["node"]) if "node" in h else None
    for k in ("node_id", "id"):
        if getattr(h, k, None) is not None:
            return getattr(h, k)
    return hit_id(h.node) if getattr(h, "node", None) is not None else None


SEARCH_METHOD: Optional[str] = None  # set via --search-method
SEARCH_NAMES = ("search", "query", "similarity_search", "semantic_search", "retrieve", "search_similar",
                "find_similar", "get_similar", "query_similar", "recall", "nearest")


SEARCH_STATS: dict = {"calls": 0, "seconds": 0.0, "warnings": Counter()}


def log(msg: str) -> None:
    print(f"[bemula-r] {msg}", file=sys.stderr, flush=True)


def vsearch(vectors: Any, q: str, k: int) -> list:
    names = [SEARCH_METHOD] if SEARCH_METHOD else [n for n in SEARCH_NAMES if callable(getattr(vectors, n, None))]
    if not names:
        public = sorted(n for n in dir(vectors) if not n.startswith("_") and callable(getattr(vectors, n)))
        raise Unsupported(f"no search-like method on VectorStore; public methods: {public}; use --search-method NAME")
    f = getattr(vectors, names[0])
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as w:  # engine warnings are counted, not printed
        warnings.simplefilter("always")
        for kw in ("top_k", "k", "n_results", "limit"):
            try:
                r = f(q, **{kw: k})
                break
            except TypeError:
                continue
        else:
            r = f(q, k)
    SEARCH_STATS["calls"] += 1
    SEARCH_STATS["seconds"] += time.perf_counter() - t0
    for x in w:
        SEARCH_STATS["warnings"][re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", "<id>", str(x.message))[:90]] += 1
    if isinstance(r, dict) and "ids" in r:  # chroma-style raw result
        r = r["ids"][0] if r["ids"] and isinstance(r["ids"][0], list) else r["ids"]
    return list(r)


def vget(vectors: Any, i: str) -> Any:
    f = getattr(vectors, "get_by_id", None)
    if not callable(f):
        raise Unsupported("VectorStore.get_by_id missing")
    return f(i)


def neighbor_ids(graph: Any, i: str) -> list:
    for name in ("get_neighbors", "neighbors", "get_edges", "edges_of"):
        f = getattr(graph, name, None)
        if callable(f):
            def ids(x):
                if isinstance(x, str):
                    return [x]
                if isinstance(x, (tuple, list, set)):
                    return [j for y in x for j in ids(y)]
                return [getattr(x, "node_id")] if getattr(x, "node_id", None) else []
            return ids(list(f(i)))
    raise Unsupported("no neighbour API on KnowledgeGraph")


def audit_verify(audit: Any) -> bool:
    for name in ("verify", "verify_chain", "verify_integrity", "is_valid"):
        f = getattr(audit, name, None)
        if callable(f):
            r = f()
            return bool(r[0] if isinstance(r, tuple) else r)
    raise Unsupported("no verify method on HashChain")


def wilson(succ: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 0.0)
    p = succ / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d * 100, (c + m) / d * 100)


class Proxy:
    """Wraps a store; intercepts mutating calls (by name) to inject faults or sabotage the engine."""

    def __init__(self, target: Any, pattern: str, mode: str):
        self._t, self._re, self._mode, self.calls = target, re.compile(pattern, re.I), mode, 0

    def __getattr__(self, name: str):
        attr = getattr(self._t, name)
        if callable(attr) and self._re.search(name):
            def wrapped(*a, **k):
                self.calls += 1
                if self._mode == "raise":
                    raise RuntimeError(f"injected fault in {name}")
                return None
            return wrapped
        return attr


# ----------------------------------------------------------------------------- corpus model
@dataclass
class Dep:
    role: str
    text: str
    session: str
    expect: str  # "forget" | "preserve"
    node: Any = None

    @property
    def id(self) -> str:
        return self.node.node_id


@dataclass
class Spec:
    idx: int
    ftype: str
    subj: int
    target: Any
    text: str
    markers: list
    needles: list
    probes: list
    deps: list
    edges: list
    informative: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    report: Any = None
    error: Optional[str] = None
    latency: float = 0.0
    probe_valid: bool = False
    pre_deleted: Optional[str] = None
    passed: bool = False
    reasons: list = field(default_factory=list)

    def dep(self, role: str) -> Optional[Dep]:
        return next((d for d in self.deps if d.role == role), None)

    @property
    def tid(self) -> str:
        return self.target.node_id


@dataclass
class Stack:
    root: Path
    graph: Any
    vectors: Any
    audit: Any
    erasure: Any
    collection: str
    specs: list
    background: list
    filesystem: Any


def mk(content: str, session: str, kind: str, turn: int = 0, properties: Optional[dict] = None) -> MemoryNode:
    return MemoryNode(
        content=content,
        source={"type": kind, "session_id": session, "turn_index": turn},
        session_id=session,
        properties=dict(properties or {}),
    )


def gen_core(rng: random.Random, ft: str, s: int, v: int) -> dict:
    """Facts with high-entropy canaries (random hex) so substring/ID collisions cannot hide or fake a leak."""
    hx = lambda n=8: "".join(rng.choice("0123456789abcdef") for _ in range(n))
    subj = rf"\b(?:customer|client|user|account) {s}\b"
    generic = f"Tell me everything about customer {s}."
    if ft == F1:
        k = f"P-{hx().upper()}"
        return dict(text=[f"Customer {s} provided official identity document passport number {k}.",
                          f"Primary verification record for client {s} lists passport identification as {k}."][v],
                    para=f"Identity check for customer {s}: passport {k} is on file.", lits=[k],
                    markers=[re.escape(k.casefold())], leaky=f"Compliance summary for customer {s}: identity verified with document {k}.",
                    probes=[f"What is the passport identity number or document code for customer {s}?", k, generic])
    if ft == F2:
        e, a = f"customer-{hx()}@enterprise.test", f"ACC-{hx().upper()}"
        return dict(text=[f"Client {s} operates primary account {a}, which routes billing notifications to {e}.",
                          f"Account {a} belongs to user {s} and uses contact address {e}."][v],
                    para=f"Billing alerts for customer {s} go to {e} (account {a}).", lits=[e, a],
                    markers=[re.escape(e.casefold()), re.escape(a.casefold())], leaky=f"Rollup for client {s}: billing contact {e}.",
                    probes=[f"Which email address or account ID is assigned to client {s}?", e, a, generic])
    if ft == F3:
        return dict(text=[f"Account records classify customer {s} under the high-priority enterprise support tier.",
                          f"Customer {s} has been designated as part of the premium-tier managed services program."][v],
                    para=f"Customer {s} is enrolled in the premium-tier support program.", lits=[],
                    markers=[rf"^(?=.*{subj})(?=.*(?:premium-tier|high-priority|enterprise support tier))"],
                    leaky=f"Account summary: customer {s} sits in the high-priority support tier.",
                    probes=[f"What support tier or category does customer {s} belong to?", f"Is customer {s} a premium or high-priority account?", generic])
    if ft == F4:
        return dict(text=[f"Customer {s} maintains an active multi-year enterprise plan, making the account eligible for priority SLA routing.",
                          f"Client {s} holds a continuous tier-1 subscription; system automatically routes support tickets to senior technical staff."][v],
                    para=f"Client {s} qualifies for priority SLA routing to senior technical engineers.", lits=[],
                    markers=[rf"^(?=.*{subj})(?=.*(?:priority sla|senior technical|tier-1 subscription|multi-year enterprise plan))"],
                    leaky=f"Rollup for client {s}: eligible for priority SLA routing.",
                    probes=[f"Is customer {s} eligible for priority SLA or senior technical routing?", f"Does client {s} have a long-term enterprise subscription?", generic])
    if ft == F5:
        r = f"R-{hx().upper()}"
        return dict(text=[f"During the Q3 2024 infrastructure migration, customer {s} deployed workstation environment {r}.",
                          f"System log audit confirms customer {s} executed production operations on host platform revision {r} throughout 2024."][v],
                    para=f"Customer {s} ran production on host revision {r} in 2024.", lits=[r], markers=[re.escape(r.casefold())],
                    leaky=f"Audit rollup: customer {s} used {r} during 2024.",
                    probes=[f"What operating system revision or workstation ID did customer {s} use in 2024?", r, generic])
    o = f"old-{hx()}@enterprise.test"
    return dict(text=[f"Primary contact for customer {s} was formerly logged as {o}.",
                      f"Legacy system records indicate user {s} email address was originally {o}."][v],
                para=f"Customer {s}'s earlier email was {o}.", lits=[o], markers=[re.escape(o.casefold())],
                leaky=f"Customer {s} active email updated to new-{hx()}@enterprise.test, replacing {o}.",
                probes=[f"What was the previous or old email address for customer {s}?", o, generic])


def make_spec(rng: random.Random, idx: int, ft: str, s: int, v: int) -> Spec:
    c = gen_core(rng, ft, s, v)
    # The benchmark models a real application identity boundary. A session is
    # not enough: unrelated memories may share it, while duplicates and
    # derived records can cross sessions. These references are what scoped
    # erasure is expected to follow.
    context_id = f"bemula:{ft}:{s}"
    entity_ref = f"customer:{s}"
    scoped = {"erasure_context_id": context_id, "entity_refs": [entity_ref]}
    tgt = mk(c["text"], f"sess_{s}_a", "target", 1, scoped)
    deps: list = []

    def add(role, text, session, expect, kind, turn):
        n = mk(text, session, kind, turn, scoped if expect == "forget" else None)
        if n.node_id == tgt.node_id or any(n.node_id == d.id for d in deps):  # content-derived IDs
            text += " (restated)"
            n = mk(text, session, kind, turn, scoped if expect == "forget" else None)
        deps.append(Dep(role, text, session, expect, n))

    sess = f"sess_{s}_a"
    add("preserved_context", f"Customer {s} requested routine usage metrics and downloaded standard documentation.", sess, "preserve", "preserved_context", 2)
    add("sibling", gen_core(rng, ft, s * 10, v)["text"], f"sess_{s * 10}_a", "preserve", "sibling_subject", 1)  # prefix-collision subject
    add("dup_verbatim", c["text"], f"sess_{s}_b", "forget", "cross_session_duplicate", 1)  # no graph edge at all
    add("dup_para", c["para"], f"sess_{s}_c", "forget", "paraphrase_duplicate", 1)
    edges = [("preserved_context", "target", "CO_OCCURRED_IN_SESSION")]
    if ft in (F2, F4):  # depth-2 derivation chain, the leaf embeds the secret
        add("derived1", f"Derived downstream record for client {s}: linked to secure parameters.", sess, "forget", "derived_fact", 3)
        add("derived2", c["leaky"], sess, "forget", "derived_rollup", 4)
        edges += [("target", "derived1", "DERIVED_FROM"), ("derived1", "derived2", "DERIVED_FROM")]
    elif ft in (F1, F3):
        add("derived1", c["leaky"], sess, "forget", "derived_summary", 3)
        edges += [("target", "derived1", "DERIVED_FROM")]
    elif ft == F5:  # distinct token: related, not the secret
        add("related_neighbor", f"Customer {s} benchmarked beta environment R-{'%08X' % rng.getrandbits(32)}-beta during setup.", sess, "preserve", "semantic_neighbor", 3)
        edges += [("target", "related_neighbor", "RELATED_TO")]
    else:  # F6: replacement record embeds the deleted old email verbatim
        add("replacement_record", c["leaky"], sess, "forget", "replacement_record", 3)
        edges += [("target", "replacement_record", "RELATED_TO")]
    return Spec(idx, ft, s, tgt, c["text"], c["markers"], c["lits"] or [c["text"]], c["probes"], deps, edges)


def build_stack(root: Path, seed: int, per_type: int, n_bg: int, tag: str) -> Stack:
    rng = random.Random(seed)
    graph = KnowledgeGraph(str(root / "knowledge_graph.json"))
    collection = f"bemula_{tag}"
    # BEMULA evaluates unlearning, not contradiction expansion. Disabling the
    # optional warning/expansion path keeps the benchmark deterministic and
    # avoids repeating an O(n) contradiction scan for every probe.
    vectors = VectorStore(
        collection_name=collection,
        persist_directory=str(root / "vectors"),
        enable_conflict_detection=False,
    )
    audit = HashChain(str(root / "audit_chain.json"))
    erasure = ErasureEngine(str(root / "blocked_inference.json"))
    filesystem = FilesystemMemory(str(root / "viking_memory"))
    subjects = rng.sample([x for x in range(1, 1000) if x % 10], per_type * len(TYPES))  # never multiples of 10
    specs, idx = [], 0
    for ft in TYPES:
        for j in range(per_type):
            idx += 1
            specs.append(make_spec(rng, idx, ft, subjects[idx - 1], j % 2))  # both templates always covered
    background = [mk(gen_core(rng, rng.choice(TYPES), 10000 + i, rng.randint(0, 1))["text"], f"sess_bg_{i}", "background", 1) for i in range(n_bg)]
    nodes = [s.target for s in specs] + [d.node for s in specs for d in s.deps] + background
    if len({n.node_id for n in nodes}) != len(nodes):
        raise RuntimeError("node_id collision in corpus")
    rng.shuffle(nodes)  # interleave: no insertion-order adjacency to exploit
    for n in nodes:
        graph.add_node(n, persist=False)
        vectors.add(n, persist=False)
        filesystem.write_entity(n)
    for s in specs:
        ids = {"target": s.tid, **{d.role: d.id for d in s.deps}}
        for a, b, t in s.edges:
            graph.add_edge(ids[a], ids[b], t, persist=False)
    graph.persist()
    vectors.persist()
    return Stack(root, graph, vectors, audit, erasure, collection, specs, background, filesystem)


# ----------------------------------------------------------------------------- execution
def do_delete(st: Stack, node_id: str, g=None, v=None, a=None):
    t = time.perf_counter()
    try:
        rep = st.erasure.delete(node_id, v or st.vectors, g or st.graph, a or st.audit,
                                reason="BEMULA rigorous unlearning request", deleted_by="bemula-rigorous-harness", semantic_cleanup=True, filesystem_store=st.filesystem)
        return rep, None, time.perf_counter() - t
    except Exception as e:  # noqa: BLE001
        return None, e, time.perf_counter() - t


def marker_hit(spec: Spec, text: str) -> bool:
    t = norm(text)
    return any(re.search(m, t, re.S) for m in spec.markers)


def probe_gate(st: Stack, top_k: int) -> None:
    for n, s in enumerate(st.specs, 1):
        if n % 10 == 0:
            log(f"probe gate {n}/{len(st.specs)}")
        s.informative = [i for i, q in enumerate(s.probes) if s.tid in {hit_id(h) for h in vsearch(st.vectors, q, top_k)}]
        s.probe_valid = bool(s.informative)


def disk_forms(lit: str) -> list:
    return [lit.encode(), lit.lower().encode(), lit.upper().encode(), lit.encode("utf-16le"), base64.b64encode(lit.encode())]


def disk_scan(root: Path, specs: list) -> dict:
    blobs = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    found = defaultdict(set)
    for s in specs:
        for needle in s.needles:
            forms = disk_forms(needle)
            for p, b in blobs.items():
                if any(f in b for f in forms):
                    found[s.idx].add(str(p.relative_to(root)))
    return found


def run_checks(spec: Spec, stage: str, graph: Any, vectors: Any, erasure: Any, top_k: int, lenient: bool, imm: bool) -> None:
    ks = (1, 5, top_k)
    forget = [d for d in spec.deps if d.expect == "forget" and not (lenient and d.role.startswith("derived") and not marker_hit(spec, d.text))]
    keep = [d for d in spec.deps if d.expect == "preserve"]

    def rec(name, status, detail=""):
        spec.checks[f"{stage}.{name}"] = (status, detail)

    def run(name, fn):
        try:
            ok, detail = fn()
            rec(name, "pass" if ok else "fail", detail)
        except Unsupported as e:
            rec(name, "unsupported", str(e))
        except Exception as e:  # noqa: BLE001
            rec(name, "fail", f"{type(e).__name__}: {e}")

    def target_inactive():
        n = graph.get_node(spec.tid)
        return (n is not None and not is_active(n)), f"state={getattr(n, 'deletion_state', 'missing')}"

    def target_scrubbed():
        n = graph.get_node(spec.tid)
        return (n is not None and not marker_hit(spec, dump(n))), "target tombstone still carries content/metadata"

    def target_vec_gone():
        return vget(vectors, spec.tid) is None, "target still in vector index"

    def deps_forgotten():
        bad = [d.role for d in forget if is_active(graph.get_node(d.id)) or vget(vectors, d.id) is not None]
        return not bad, f"dependents still live: {bad}"

    def no_content_leak():
        bad = []
        for who, i in [("target", spec.tid)] + [(d.role, d.id) for d in spec.deps]:
            gn, vn = graph.get_node(i), vget(vectors, i)
            if is_active(gn) and marker_hit(spec, dump(gn)):
                bad.append(f"{who}@graph")
            if vn is not None and marker_hit(spec, text_of(vn) + " " + dump(vn)):
                bad.append(f"{who}@vector")
        return not bad, f"secret present in: {bad}"

    def probes_clean():
        bad = []
        fids = {spec.tid} | {d.id for d in forget}
        owned = fids | {d.id for d in keep}
        for pi, q in enumerate(spec.probes):
            hits = vsearch(vectors, q, max(ks))
            for k in ks:
                for h in hits[:k]:
                    hid = hit_id(h)
                    txt = text_of(h[0] if isinstance(h, (tuple, list)) else h)
                    if hid in fids:
                        bad.append(f"probe{pi}@k{k}: forgotten id {hid[:8]}")
                    elif hid in owned and not is_active(graph.get_node(hid)):
                        bad.append(f"probe{pi}@k{k}: inactive id {hid[:8]}")
                    elif marker_hit(spec, txt + " " + dump(vget(vectors, hid)) if hid else txt):
                        bad.append(f"probe{pi}@k{k}: secret in hit text")
        return not bad, "; ".join(bad[:4])

    def preserve_ok():
        bad = []
        for d in keep:
            gn, vn = graph.get_node(d.id), vget(vectors, d.id)
            if not is_active(gn):
                bad.append(f"{d.role}:graph-inactive")
            elif getattr(gn, "content", d.text) != d.text:
                bad.append(f"{d.role}:content-altered")
            if vn is None:
                bad.append(f"{d.role}:vector-missing")
        return not bad, f"collateral damage: {bad}"

    def preserve_retrievable():
        bad = [d.role for d in keep if d.id not in {hit_id(h) for h in vsearch(vectors, d.text, top_k)}]
        return not bad, f"unretrievable: {bad}"

    def dangling_edges():
        bad = [d.role for d in keep if spec.tid in neighbor_ids(graph, d.id)]
        return not bad, f"edges still reference deleted target: {bad}"

    def blocked():
        b = getattr(erasure, "blocked_ids", None)
        if b is None:
            raise Unsupported("erasure.blocked_ids missing")
        return spec.tid in b, "target not in blocked set"

    for name, fn in [("target_inactive", target_inactive), ("target_scrubbed", target_scrubbed), ("target_vec_gone", target_vec_gone),
                     ("deps_forgotten", deps_forgotten), ("no_content_leak", no_content_leak), ("probes_clean", probes_clean),
                     ("preserve_ok", preserve_ok), ("preserve_retrievable", preserve_retrievable),
                     ("dangling_edges", dangling_edges), ("blocked", blocked)]:
        run(name, fn)
    if imm:
        rec("delete_no_exception", "fail" if spec.error else "pass", spec.error or "")
        risks = list(getattr(spec.report, "residual_risks", []) or [])
        rec("report_clean", "fail" if risks else "pass", f"{len(risks)} residual risks reported")


def verdict(specs: list, allow_unsupported: bool) -> dict:
    fail_ctr, unsup, vacuous = Counter(), Counter(), 0
    for s in specs:
        bad = []
        for k, (st, _) in s.checks.items():
            b = k.split(".", 1)[1]
            if b in ADVISORY:
                continue
            if st == "fail" or (st == "unsupported" and not allow_unsupported):
                bad.append(k)
            if st == "unsupported":
                unsup[k] += 1
        if not s.probe_valid:
            bad.append("probe_gate.vacuous")
            vacuous += 1
        s.reasons, s.passed = bad, not bad
        fail_ctr.update(bad)
    n = len(specs)
    p = sum(s.passed for s in specs)
    lo, hi = wilson(p, n)
    return dict(instances=n, passed=p, rpr=round(p / n * 100, 2) if n else 0.0, wilson95=[round(lo, 2), round(hi, 2)],
                silent_leaks=sum(1 for s in specs if _leaks(s) and not _disclosed(s)),
                disclosed_leaks=sum(1 for s in specs if _leaks(s) and _disclosed(s)),
                vacuous_probe_instances=vacuous, failing_checks=dict(fail_ctr.most_common()), unsupported_checks=dict(unsup))


def _leaks(s: Spec) -> bool:
    return any(k.split(".", 1)[1] in LEAK_CHECKS and st == "fail" for k, (st, _) in s.checks.items())


def _disclosed(s: Spec) -> bool:
    return bool(s.error or getattr(s.report, "residual_risks", None))


def per_type(specs: list) -> dict:
    out = {}
    for t in TYPES:
        g = [s for s in specs if s.ftype == t]
        out[t] = dict(passed=sum(s.passed for s in g), total=len(g), rpr=round(sum(s.passed for s in g) / len(g) * 100, 2) if g else 0)
    return out


# ----------------------------------------------------------------------------- main evaluation
def evaluate(a: argparse.Namespace, root: Path) -> dict:
    SEARCH_STATS["calls"] = 0
    SEARCH_STATS["seconds"] = 0.0
    SEARCH_STATS["warnings"] = Counter()
    log("building corpus ...")
    st = build_stack(root, a.seed, a.per_type, a.background, "main")
    if getattr(a, "quick", False):
        # Keep one semantic and one exact probe per instance so quick mode is
        # still meaningful without performing the full production probe set.
        for spec in st.specs:
            spec.probes = spec.probes[:2]
    t0 = time.perf_counter()
    for q in st.specs[0].probes:
        vsearch(st.vectors, q, a.top_k)
    per = (time.perf_counter() - t0) / len(st.specs[0].probes)
    probe_count = sum(len(spec.probes) for spec in st.specs)
    estimated_searches = probe_count + len(st.specs) * 8 + min(40, len(st.background))
    est = estimated_searches * per
    log(f"{len(st.graph.nodes) if hasattr(st.graph, 'nodes') else '?'} nodes indexed; one search = {per * 1000:.0f} ms; "
        f"~{estimated_searches} bounded searches in the main run => ~{est / 60:.1f} min")
    probe_gate(st, a.top_k)
    pre_found = disk_scan(root, st.specs[:20])
    caveats = []
    if not pre_found:
        caveats.append("Pre-deletion disk scan found no plaintext secrets on disk: disk_clean may be vacuous (store not flushed or encrypted).")
    log("deleting ...")
    order = list(st.specs)
    random.Random(a.seed + 1).shuffle(order)
    lat, warns = [], Counter()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        for s in order:
            if s.idx % 4 == 0 and s.dep("derived1"):  # out-of-order: delete mid-chain node first, then the source
                s.pre_deleted = "derived1"
                do_delete(st, s.dep("derived1").id)
            s.report, err, s.latency = do_delete(st, s.tid)
            s.error = f"{type(err).__name__}: {err}" if err else None
            lat.append(s.latency)
        for x in w:
            warns[str(x.message)[:80]] += 1
    log("immediate post-deletion checks ...")
    for n, s in enumerate(st.specs, 1):
        if n % 10 == 0:
            log(f"checked {n}/{len(st.specs)}")
        run_checks(s, "imm", st.graph, st.vectors, st.erasure, a.top_k, a.lenient_derived, True)

    # collateral damage on untouched background population
    bg_bad = 0
    sample = random.Random(a.seed + 2).sample(st.background, min(40, len(st.background)))
    for n in sample:
        ok = is_active(st.graph.get_node(n.node_id)) and vget(st.vectors, n.node_id) is not None
        ok = ok and n.node_id in {hit_id(h) for h in vsearch(st.vectors, n.content, a.top_k)}
        bg_bad += (not ok)

    # edge cases: idempotency, unknown ids, audit integrity and tamper-evidence
    edge = {}
    again = random.Random(a.seed + 3).sample(st.specs, min(10, len(st.specs)))
    size0 = (root / "audit_chain.json").stat().st_size if (root / "audit_chain.json").exists() else 0
    errs = [do_delete(st, s.tid)[1] for s in again]
    edge["redelete_exceptions"] = sum(e is not None for e in errs)
    edge["redelete_state_stable"] = all(not is_active(st.graph.get_node(s.tid)) and all(is_active(st.graph.get_node(d.id)) for d in s.deps if d.expect == "preserve") for s in again)
    edge["audit_bytes_growth_on_redelete"] = ((root / "audit_chain.json").stat().st_size - size0) if (root / "audit_chain.json").exists() else None
    graceful = True
    for bogus in ("does-not-exist-0000", ""):
        _, e, _ = do_delete(st, bogus)
        graceful &= e is None or isinstance(e, (KeyError, ValueError, LookupError))
    edge["unknown_id_graceful"] = graceful
    try:
        edge["audit_chain_valid"] = audit_verify(st.audit)
    except Unsupported as e:
        edge["audit_chain_valid"] = f"unsupported: {e}"
    edge["audit_tamper_detected"] = tamper_test(root)

    # persistence: cold reload from disk
    log("cold reload checks ...")
    reload_ok = True
    try:
        g2 = KnowledgeGraph(str(root / "knowledge_graph.json"))
        v2 = VectorStore(
            collection_name=st.collection,
            persist_directory=str(root / "vectors"),
            enable_conflict_detection=False,
        )
        e2 = ErasureEngine(str(root / "blocked_inference.json"))
        if g2.get_node(st.background[0].node_id) is None:
            caveats.append("Cold reload of KnowledgeGraph is empty: state is not persisted without an explicit save().")
        for s in st.specs:
            run_checks(s, "reload", g2, v2, e2, a.top_k, a.lenient_derived, False)
    except Exception as e:  # noqa: BLE001
        reload_ok = False
        caveats.append(f"Cold reload failed: {type(e).__name__}: {e}")
        for s in st.specs:
            s.checks["reload.cold_start"] = ("fail", str(e))

    # audit presence and on-disk residue, per instance
    audit_txt = (root / "audit_chain.json").read_text(errors="ignore") if (root / "audit_chain.json").exists() else ""
    audit_knows_ids = any(s.tid in audit_txt for s in st.specs)
    found = disk_scan(root, st.specs)
    for s in st.specs:
        s.checks["global.audit_entry"] = (("pass" if s.tid in audit_txt else "fail") if audit_knows_ids else "unsupported", "no audit record for erased node")
        s.checks["global.disk_clean"] = ("fail" if found.get(s.idx) else "pass", f"residue in {sorted(found.get(s.idx, []))}")
    res = verdict(st.specs, a.allow_unsupported)
    res.update(per_type=per_type(st.specs), edge_cases=edge, background_collateral_failures=bg_bad,
               latency_ms=dict(p50=round(sorted(lat)[len(lat) // 2] * 1000, 2), p95=round(sorted(lat)[int(len(lat) * .95) - 1] * 1000, 2)),
               warnings_emitted=dict(warns), caveats=caveats, reload_ok=reload_ok,
               disk_residue_files=sorted({f for fs in found.values() for f in fs}),
               search_stats=dict(calls=SEARCH_STATS["calls"], mean_ms=round(SEARCH_STATS["seconds"] / max(1, SEARCH_STATS["calls"]) * 1000, 1),
                                 engine_warnings=dict(SEARCH_STATS["warnings"])))
    res["failures"] = [dict(instance=s.idx, type=s.ftype, reasons=s.reasons,
                            details={k: v[1] for k, v in s.checks.items() if k in s.reasons and v[1]}) for s in st.specs if not s.passed]
    return res


def tamper_test(root: Path) -> Any:
    p = root / "audit_chain.json"
    if not p.exists():
        return "unsupported: no audit file"
    raw = p.read_text()
    m = list(re.finditer(r"[0-9a-f]{64}", raw))
    if len(m) < 2:
        return "unsupported: no hash fields found"
    pos = m[len(m) // 2].start()
    forged = raw[:pos] + ("0" if raw[pos] != "0" else "1") + raw[pos + 1:]
    tmp = Path(tempfile.mkdtemp()) / "audit_tampered.json"
    tmp.write_text(forged)
    try:
        return not audit_verify(HashChain(str(tmp)))
    except Unsupported as e:
        return f"unsupported: {e}"
    except Exception:  # noqa: BLE001
        return True  # refusing to load a tampered chain counts as detection
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


# ----------------------------------------------------------------------------- stress scenarios
def scenario(kind: str, a: argparse.Namespace) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"bemula_{kind[:6]}_") as d:
        root = Path(d)
        st = build_stack(root, a.seed + 101, a.small_per_type, 40, "s" + str(abs(hash(kind)) % 10**6))
        probe_gate(st, a.top_k)
        extra: dict = {}
        if kind == "concurrent":
            def work(s):
                s.report, err, s.latency = do_delete(st, s.tid)
                s.error = f"{type(err).__name__}: {err}" if err else None
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(work, st.specs))
        elif kind == "fault_injection":
            loud = silent = applicable = 0
            for s in st.specs:
                vp = Proxy(st.vectors, r"delete|remove|purge|erase|drop", "raise")
                rep, err, _ = do_delete(st, s.tid, v=vp)
                applicable += vp.calls > 0
                loud += err is not None
                silent += (err is None and not getattr(rep, "residual_risks", None) and vget(st.vectors, s.tid) is not None)
            for s in st.specs:  # retry with healthy stores: must fully recover
                s.report, err, s.latency = do_delete(st, s.tid)
                s.error = f"{type(err).__name__}: {err}" if err else None
            extra = dict(fault_applicable=applicable > 0, loud_failures=loud, silent_failures=silent)
        elif kind.startswith("mutant:"):
            mode = kind.split(":", 1)[1]
            pat = {"vector_noop": ("vec", r"delete|remove|purge|erase|drop"), "graph_noop": ("graph", r"get_node|delete|remove|tombstone|mark|erase|purge|redact|scrub"),
                   "audit_noop": ("audit", r"append|add|record|log|write")}[mode]
            expected = {"vector_noop": "imm.target_vec_gone", "graph_noop": "imm.target_inactive", "audit_noop": "global.audit_entry"}[mode]
            calls = 0
            for s in st.specs:
                px = Proxy({"vec": st.vectors, "graph": st.graph, "audit": st.audit}[pat[0]], pat[1], "noop")
                kw = {"vec": "v", "graph": "g", "audit": "a"}[pat[0]]
                s.report, err, s.latency = do_delete(st, s.tid, **{kw: px})
                s.error = f"{type(err).__name__}: {err}" if err else None
                calls += px.calls
            extra = dict(mutation_applicable=calls > 0, expected_check=expected)
        else:  # control
            for s in st.specs:
                s.report, err, s.latency = do_delete(st, s.tid)
                s.error = f"{type(err).__name__}: {err}" if err else None
        for s in st.specs:
            run_checks(s, "imm", st.graph, st.vectors, st.erasure, a.top_k, a.lenient_derived, True)
        audit_txt = (root / "audit_chain.json").read_text(errors="ignore") if (root / "audit_chain.json").exists() else ""
        for s in st.specs:
            s.checks["global.audit_entry"] = (("pass" if s.tid in audit_txt else "fail") if any(x.tid in audit_txt for x in st.specs) else "unsupported", "")
        v = verdict(st.specs, a.allow_unsupported)
        v.update(extra)
        if kind == "concurrent":
            v["worker_exceptions"] = sum(1 for s in st.specs if s.error)
            try:
                v["audit_chain_valid"] = audit_verify(st.audit)
            except Unsupported as e:
                v["audit_chain_valid"] = f"unsupported: {e}"
        return v


# ----------------------------------------------------------------------------- reporting
def render_md(res: dict, mut: dict, scen: dict, a: argparse.Namespace) -> str:
    L = ["# BEMULA-R: Rigorous Adversarial Unlearning Evaluation", "",
         f"- Target instances: **{res['instances']}** (+{a.background} untouched background nodes), seed {a.seed}, top-k {a.top_k}",
         f"- **RPR: {res['rpr']:.2f}%** ({res['passed']}/{res['instances']}), Wilson 95% CI [{res['wilson95'][0]}%, {res['wilson95'][1]}%]",
         f"- Silent leaks (leak with no engine disclosure): **{res['silent_leaks']}**; disclosed leaks: {res['disclosed_leaks']}",
         f"- Vacuous instances (no probe found target pre-deletion): {res['vacuous_probe_instances']}",
         f"- Background collateral failures: {res['background_collateral_failures']}/{min(40, a.background)}; delete latency p50/p95: {res['latency_ms']['p50']}/{res['latency_ms']['p95']} ms",
         "", "## Per-type", ""]
    L += [f"- {t}: {v['passed']}/{v['total']} ({v['rpr']:.2f}%)" for t, v in res["per_type"].items()]
    ss = res["search_stats"]
    L += [f"- Retrieval calls: {ss['calls']} (mean {ss['mean_ms']} ms); engine warnings during retrieval: {sum(ss['engine_warnings'].values())}"]
    L += ["", "## Failing checks (instances affected)", ""]
    L += [f"- `{k}`: {v}" for k, v in res["failing_checks"].items()] or ["- none"]
    if res["unsupported_checks"]:
        L += ["", "## Unsupported (stack lacks capability; counted as FAIL unless --allow-unsupported)", ""]
        L += [f"- `{k}`: {v}" for k, v in res["unsupported_checks"].items()]
    L += ["", "## Edge cases", ""] + [f"- {k}: {v}" for k, v in res["edge_cases"].items()]
    L += ["", "## Stress scenarios", ""]
    for k, v in scen.items():
        extras = {x: y for x, y in v.items() if x not in ("failing_checks", "unsupported_checks", "wilson95")}
        L.append(f"- **{k}**: {extras}")
    L += ["", "## Harness self-test (mutation kill rate; must be high or the harness is vacuous)", ""]
    for k, v in mut.items():
        L.append(f"- {k}: {v}")
    if res["disk_residue_files"]:
        L += ["", "## Plaintext residue on disk after erasure", ""] + [f"- {f}" for f in res["disk_residue_files"]]
    if res["caveats"]:
        L += ["", "## Caveats", ""] + [f"- {c}" for c in res["caveats"]]
    L += ["", "## Definition", "",
          "An instance passes only if, both immediately and after cold reload: the target is inactive and scrubbed; every dependent "
          "(derived, replacement, cross-session and paraphrased duplicates) is forgotten; no active node, vector hit or on-disk byte "
          "contains the secret; adversarial probes at k=1/5/top-k retrieve nothing forgotten; the block and audit records exist; "
          "and every preserve-labelled node (context, prefix-collision sibling, neighbour) is intact, unaltered and still retrievable."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=17)
    ap.add_argument("--background", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--top-k", type=int, default=25)
    ap.add_argument("--small-per-type", type=int, default=3)
    ap.add_argument("--allow-unsupported", action="store_true")
    ap.add_argument("--lenient-derived", action="store_true", help="allow clean (secret-free) derived nodes to survive")
    ap.add_argument("--skip-scenarios", action="store_true")
    ap.add_argument("--quick", action="store_true", help="six instances, 12 background nodes, no stress scenarios unless --with-scenarios")
    ap.add_argument("--with-scenarios", action="store_true", help="also run the slower control/concurrency/fault/mutation scenarios in quick mode")
    ap.add_argument("--search-method", default=None, help="name of the VectorStore retrieval method")
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()
    if a.quick:
        a.per_type, a.background, a.small_per_type = 1, 12, 1
        if not a.with_scenarios:
            a.skip_scenarios = True
    global SEARCH_METHOD
    SEARCH_METHOD = a.search_method

    with tempfile.TemporaryDirectory(prefix="bemula_rigorous_") as d:
        res = evaluate(a, Path(d))
    scen, mut = {}, {}
    if not a.skip_scenarios:
        control = scenario("control", a)
        for k in ("concurrent", "fault_injection"):
            scen[k] = scenario(k, a)
        for m in ("vector_noop", "graph_noop", "audit_noop"):
            v = scenario(f"mutant:{m}", a)
            if v.get("mutation_applicable") is False:
                mut[m] = "inapplicable (no intercepted calls; engine uses other method names)"
            else:
                exp = v["expected_check"]
                kill = round(v["failing_checks"].get(exp, 0) / v["instances"] * 100, 2)
                base = control["failing_checks"].get(exp, 0)
                mut[m] = f"`{exp}` caught {kill}% of sabotaged deletions (control false-alarms: {base})" + ("" if kill >= 90 and base == 0 else "  <-- HARNESS TOO WEAK")
        scen["control"] = control
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bemula_rigorous_report.json").write_text(json.dumps(dict(main=res, scenarios=scen, mutation=mut), indent=2, default=str), encoding="utf-8")
    md = render_md(res, mut, scen, a)
    (out / "bemula_rigorous_results.md").write_text(md, encoding="utf-8")
    print(md)
    bad = res["passed"] != res["instances"] or any(v["passed"] != v["instances"] for v in scen.values()) \
        or any("TOO WEAK" in str(v) for v in mut.values()) or res["edge_cases"]["redelete_exceptions"] > 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
