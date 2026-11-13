# MNEMOSYNE architecture

MNEMOSYNE is an entity-first memory system. A `MemoryNode` is created once and its UUID connects the same memory across sessions, graph relationships, vector retrieval, filesystem storage, capsules, and audit records.

## A3 architecture sheet

![MNEMOSYNE implemented architecture](docs/mnemosyne-architecture-a3.svg)

- [Download the A3 SVG](docs/mnemosyne-architecture-a3.svg)
- [Download the printable A3 PDF](docs/mnemosyne-architecture-a3.pdf)

## High-level view

### Harnesses

`AgentA` is the main memory harness. It remembers information, commits sessions, recalls context, performs deletion, runs dreaming/consolidation, and exports memory capsules.

`AgentB` imports a capsule from another harness. Normal recall is fail-closed when the capsule contains deletion blocks; `recall_full()` can inspect surviving alternatives explicitly.

### Memory identity

Each memory is a `MemoryNode`. It contains the node UUID, session ID, content, properties, trust status, summaries, lifecycle events, relationships, and deletion state.

### Hybrid memory

- `KnowledgeGraph` stores entities and typed relationships.
- `GraphStore` exposes the graph-healing and session-commit contract.
- `VectorStore` uses FAISS for semantic retrieval.
- `FilesystemMemory` stores inspectable JSON entity records.
- `SessionStore` keeps session membership and commit metadata.

### Accountability

`ErasureEngine` coordinates deletion. `HashChain` records tamper-evident operations, `ErasureJournal` tracks interrupted work, `ErasureRecovery` retries incomplete operations, and `GraphHealer` repairs or quarantines orphaned graph nodes.

## Mid-level flows

### 1. Remember and commit

1. `AgentA.remember()` creates a `MemoryNode`.
2. The node is written to the graph and FAISS vector store.
3. Session membership and the creation event are recorded.
4. `commit_session()` writes filesystem memory, runs entity extraction, and invokes graph healing.
5. Summaries and extraction use deterministic fallbacks when no LLM provider is enabled.

### 2. Recall and context transfer

1. A harness sends a query to `ContextBuilder`.
2. `VectorStore` finds semantically relevant nodes.
3. The knowledge graph expands the result through active ancestors and descendants.
4. `AbstentionEngine` and `ContradictionEngine` help prevent unsafe or conflicting recall.
5. `ActiveContext` applies the token budget and returns the selected context.
6. For handoff, `CapsuleExporter` packages nodes, graph state, vectors, lifecycle data, and audit information. `CapsuleImporter` validates and restores that state for another agent.

### 3. Scoped deletion and recovery

1. `AgentA.forget()` calls `ErasureEngine` with the target UUID and optional `context_id` or `entity_refs`.
2. The engine builds a deletion manifest before mutating anything. It follows derived records, explicit references, supersession links, exact fingerprints, and the requested context.
3. The target and its dependent records are scrubbed in the graph, vector store, filesystem memory, and session store.
4. Their UUIDs are added to the inference block list and graph edges are removed.
5. The operation records who deleted the entity, why, when, what IDs were affected, and a content digest in the audit chain.
6. If an interruption occurs, `ErasureRecovery` uses the journal and blocked IDs to finish projection cleanup on retry.

## Low-level records

| Component | Stores or controls |
| --- | --- |
| `MemoryNode` | UUID, session, content, summaries, trust, properties, relationships, lifecycle, deletion state |
| `SessionStore` | Session status, committed actor/time, and entity UUID membership |
| `KnowledgeGraph` | Entity records and typed graph edges in `knowledge_graph.json` |
| `VectorStore` | FAISS embeddings and metadata JSON for semantic retrieval |
| `FilesystemMemory` | JSON entity snapshots under `viking_memory` |
| `HashChain` | Append-only tamper-evident audit entries in `audit_log.json` |
| `ErasureJournal` | In-progress, advanced, completed, and failed deletion operations |
| Capsule files | Portable nodes, vectors, graph edges, lifecycle, sessions, deletion audit, and risk data |

## Optional provider paths

The core system works without an LLM. When configured, `ConfiguredLLM` can use Groq or Ollama for:

- entity extraction;
- generated summaries;
- orphan-link suggestions;
- ambiguous dreaming decisions.

`HonchoDreaming` uses the local Laya gate first and escalates unresolved cases to the configured provider. Deterministic evidence checks and fallback behavior remain available when the provider is disabled or unavailable.

## Implementation boundary

The diagram and this document describe the implemented repository components. BEMULA-R validates the storage and retrieval erasure path immediately and after cold reload; its benchmark result should be read as evidence for that tested path, not as a guarantee against every external cache or deployment-specific integration.
