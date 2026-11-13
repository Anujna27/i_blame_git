# MNEMOSYNE Architecture Context for Claude

Use this document as the authoritative context for understanding the current MNEMOSYNE implementation. Describe only what is implemented in the repository. Do not present planned or partially implemented capabilities as production-ready.

## Project purpose

MNEMOSYNE is an auditable memory system for coding agents. It stores session-scoped entities, retrieves context using both vector similarity and graph relationships, tracks entity lifecycle, supports agent handoff, and provides deletion accountability with residual-risk reporting.

The main design goal is not only remembering information. It is making memory inspectable, scoped, transferable, and honest about what deletion did or did not remove.

## High-level architecture

```text
User or coding agent
        |
        v
Agent harness: AgentA / AgentB
        |
        v
MemoryNode identity
   |       |        |          |
   v       v        v          v
Session  Knowledge  FAISS    Filesystem
Store    Graph      vectors  memory
        |
        v
ErasureEngine + HashChain + ErasureJournal + GraphHealer
```

Every representation is connected by the same `MemoryNode.node_id` UUID.

## Implemented components

### AgentA

File: `agents/agent_a.py`

The primary harness and application coordinator. It provides operations for:

- remembering entities;
- updating entities;
- committing sessions;
- building bounded context;
- deleting entities;
- exporting capsules;
- running graph healing;
- recovering pending erasures;
- reading LLM telemetry.

### AgentB

File: `agents/agent_b.py`

The handoff/import harness. It imports a capsule from AgentA and restores:

- memory nodes;
- blocked deletion IDs;
- residual-risk metadata;
- vector snapshots.

AgentB is a portability demonstration and has a simpler retrieval path than AgentA.

### MemoryNode

File: `core/memory_node.py`

The canonical memory entity. It contains:

- UUID identity;
- content;
- source/session metadata;
- entity type;
- properties;
- trust status;
- contradiction references;
- derivation edges;
- version;
- lifecycle history;
- deletion state;
- deletion actor, reason, and timestamp;
- L0/L1/L2 summaries.

### SessionStore

File: `stores/session_store.py`

Stores session metadata and entity membership. It answers which entities belong to a session and whether the session has been committed.

It is not the primary content store.

### KnowledgeGraph

File: `core/knowledge_graph.py`

NetworkX-backed directed graph persisted as JSON. It stores entities and relationships such as:

- `PREFERS`;
- `OWNS`;
- `DERIVED_FROM`;
- `CONTRADICTS`;
- `RELATED_TO`;
- `SESSION_MEMBER`;
- `MENTIONS`.

Only explicit `DERIVED_FROM` relationships should cause dependent invalidation during deletion. Associative relationships such as `RELATED_TO` must not automatically cause collateral deletion.

### VectorStore

File: `stores/vector_store.py`

FAISS-backed semantic retrieval. It stores embeddings, entity IDs, active metadata, trust metadata, and serialized node metadata.

It is used for:

- semantic retrieval;
- hybrid context construction;
- residual semantic-risk detection;
- vector deletion;
- capsule vector snapshots.

### FilesystemMemory

File: `stores/filesystem_memory.py`

Inspectable filesystem-backed memory with `viking://`-style references. It stores JSON entity records, including L0/L1/L2 content, usually during session commit.

The deletion path now supports removal of target and invalidated-child filesystem records.

### ContextBuilder and ActiveContext

File: `core/active_context.py`

`ContextBuilder` combines:

1. vector search results;
2. graph-related entities;
3. session filtering;
4. active/deleted filtering;
5. token-budget selection.

It returns `ActiveContext`, which includes selected entities, token count, vector IDs, graph IDs, and ranking explanations.

### SummaryGenerator

File: `core/summary_generator.py`

Creates:

- `summary_l0`: compact summary;
- `summary_l1`: contextual summary;
- `content_l2`: full content.

With an LLM, summaries are generated. Without an LLM, the fallback selects the first sentence for L0, the first four sentences for L1, truncates them to configured limits, and preserves the full input as L2.

### EntityExtractor

File: `core/entity_extractor.py`

Runs during session commit. It supports optional LLM-assisted extraction and deterministic fallback behavior.

### ConfiguredLLM

File: `core/llm_config.py`

Provider adapter for Groq and OpenAI-compatible endpoints. It handles provider configuration, JSON responses, retries, failures, and token telemetry.

LLM use is optional. The application must remain usable when the provider is disabled or unavailable.

### ErasureEngine

File: `core/erasure_engine.py`

Coordinates deletion across storage layers. Its implemented phases are:

1. source removal;
2. derived-artifact invalidation;
3. persistent inference blocking;
4. semantic-neighbor risk checking;
5. restoration-status reporting;
6. graph/vector/filesystem redaction and persistence.

It returns an `ErasureReport` with levels, verdict, residual risks, timestamp, actor, reason, and signature.

Semantic cleanup is conservative. It removes high-confidence exact sensitive-token copies when enabled, but ambiguous semantic neighbors remain disclosed as residual risks rather than being blindly deleted.

### ErasureJournal and ErasureRecovery

Files:

- `core/erasure_journal.py`;
- `core/erasure_recovery.py`.

The journal records deletion operations before mutation and tracks phases such as `started`, `mutating`, `failed`, and `completed`.

`ErasureRecovery` checks pending operations after restart. It resumes active deletions or verifies already-mutated graph, vector, filesystem, and inference-block state.

### HashChain

File: `core/hash_chain.py`

The hash chain stores tamper-evident lifecycle and deletion events. Each event includes:

- operation;
- entity ID;
- actor;
- reason;
- timestamp;
- previous hash;
- current hash;
- operation details.

It detects audit tampering but does not prevent file access or unauthorized mutations.

### GraphHealer

File: `core/graph_healer.py`

Detects and repairs graph problems such as:

- orphan nodes;
- deleted-parent children;
- invalid targets;
- orphaned sessions;
- duplicate candidates.

It performs deterministic checks first. Optional LLM link suggestions are proposals only. Uncertain nodes are quarantined rather than silently deleted.

### Capsules

Files:

- `capsule/export.py`;
- `capsule/import_capsule.py`;
- `capsule/validator.py`.

A capsule is a structured JSON handoff package containing entities, lifecycle history, graph edges, session commits, vector snapshots, deletion audit, blocked IDs, residual risks, and hash-chain data.

## Main process flows

### Remember

```text
input text
  -> create MemoryNode
  -> generate L0/L1/L2
  -> detect contradictions
  -> write VectorStore
  -> write KnowledgeGraph
  -> update SessionStore
  -> append HashChain event
```

### Commit session

```text
collect session entities
  -> entity extraction
  -> write FilesystemMemory records
  -> mark session committed
  -> append commit audit event
  -> run graph healing
```

### Retrieve context

```text
query
  -> FAISS vector search
  -> session filtering
  -> graph expansion
  -> active/deleted filtering
  -> token-budget selection
  -> ActiveContext for harness
```

### Delete

```text
delete request
  -> begin ErasureJournal entry
  -> remove source from active retrieval
  -> invalidate DERIVED_FROM descendants
  -> remove vectors
  -> remove filesystem copies
  -> add inference block
  -> find semantic residual risks
  -> redact graph content and edges
  -> persist state
  -> append HashChain event
  -> complete journal entry
```

### Agent handoff

```text
AgentA
  -> CapsuleExporter
  -> validated JSON capsule
  -> CapsuleImporter
  -> AgentB
```

## Implemented protocol envelope

File: `core/harness_protocol.py`

The transport-neutral message envelope supports these commands:

```text
REMEMBER
COMMIT_SESSION
QUERY
DELETE_ENTITY
EXPORT_CAPSULE
IMPORT_CAPSULE
HEALTH
```

It validates command names, sender identity, payload shape, correlation ID, timestamp, and protocol version. It does not yet provide authentication, authorization, encryption, or replay protection.

## Testing and benchmarks

The repository contains:

- standard unit and integration tests under `tests/`;
- claim tests under `tests/claims/`;
- adversarial tests under `tests/adversarial/`;
- BEMULA-style evaluation scripts;
- rigorous deletion and semantic-leak reports.

The meaningful deletion metric is:

```text
RPR = fully passed deletion requests / total deletion requests × 100
```

An adversarial request passes only when immediate retrieval, cold reload, graph state, vector state, filesystem state, dependency cleanup, probe retrieval, audit, and preservation checks all pass.

## Current honest status

Validated capabilities:

- session-scoped memory;
- graph and vector hybrid retrieval;
- lifecycle tracking;
- deletion accountability;
- filesystem-memory deletion path;
- deletion journaling and recovery visibility;
- capsule handoff;
- graph healing;
- optional Groq LLM integration;
- audit tamper detection;
- deterministic fallback behavior;
- standard test suite passing in isolated runs.

Not production-complete:

- rigorous BEMULA-R deletion pass rate is still zero;
- paraphrased and temporal semantic leaks remain;
- cross-process locking is incomplete;
- fault-injection recovery needs broader validation;
- JSON/FAISS multi-store updates are not fully transactional;
- graph mutation testing needs stronger assertions;
- harness authentication and authorization are not implemented;
- repeated deletion still creates audit growth that needs optimization.

## Guidance for Claude

When proposing changes:

1. Preserve the shared `MemoryNode.node_id` identity across every store.
2. Do not treat `RELATED_TO` as a deletion dependency.
3. Do not claim deletion success without checking graph, vectors, filesystem, restart state, and probes.
4. Do not delete ambiguous semantic neighbors automatically.
5. Preserve audit evidence while removing sensitive content.
6. Keep LLM features optional and retain deterministic fallback paths.
7. Use isolated temporary stores for benchmarks.
8. Do not call the system production-ready while BEMULA-R has silent leaks, disk residue, or failed recovery checks.
