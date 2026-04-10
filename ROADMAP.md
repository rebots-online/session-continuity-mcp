# ROADMAP — From Local MCP to hybrid Knowledge Graph

> Status: v1.0 is **deployed and working**. The hKG architecture is in design.

## Current State (v1.0 — Local SQLite + Pieces LTM)

```
AI Tool (Claude Code, Windsurf, Roo, Codex, Gemini)
    │
    ▼ MCP stdio
┌──────────────────────┐
│  session-continuity  │
│  -mcp server.py      │
│  (single Python file │
│   stdlib only)       │
├──────────────────────┤
│  context.db (SQLite) │  ← session intents, entity registry, checklist cache,
│                      │    project registry, project keywords
├──────────────────────┤
│  Pieces LTM (SQLite) │  ← read-only, optional — workstream events and summaries
│                      │    from Pieces for Developers desktop app
├──────────────────────┤
│  git (subprocess)    │  ← branch, log, status, diff
│  CHECKLIST.md (file) │  ← single source of truth for task state
└──────────────────────┘
```

### Pieces LTM Dependency

The current implementation optionally reads from the Pieces for Developers local
SQLite database (`~/Documents/com.pieces.os/.../db.sqlite3`). This provides:

- **Session history**: which projects were worked on, when, and in which AI tool
  (derived from OS window titles — high fidelity)
- **Summary search**: full-text search over Pieces' auto-generated session summaries

**Limitations of the current Pieces integration:**

1. **Local only** — each machine has its own Pieces database with no built-in sync.
   Pieces backup/restore is destructive (replaces, doesn't merge).
2. **Read-only** — the server queries Pieces but cannot write to it. Session intents
   and entity registrations live only in context.db.
3. **Optional** — without Pieces, `get_recent_sessions` and `search_history` return
   empty results. All other tools work normally.
4. **FTS-only search** — Pieces summaries are matched by keyword, not by semantic
   similarity. No vector embeddings, no relationship inference.

## Planned: hybrid Knowledge Graph (hKG) Architecture

The long-term vision replaces the local SQLite stores with a networked hybrid
Knowledge Graph that supports semantic search, ontological reasoning, and
cross-machine synchronization.

### Target Architecture

```
AI Tools (any machine)
    │
    ▼ MCP stdio/http
┌─────────────────────────────────────────────────────────┐
│                  session-continuity-mcp v2                │
│                   (MCP query interface)                   │
├─────────────────────────────────────────────────────────┤
│                        Cognee                            │
│  (entity extraction · relationship inference · RAG)      │
│  + Docling (PDF/DOCX/image → structured text)            │
├───────────┬───────────┬─────────────┬───────────────────┤
│  Neo4j    │  Qdrant   │ PostgreSQL  │     Redis          │
│  (graph + │ (bulk vec │ (UUID auth  │  (cache + pub/sub  │
│  vectors  │  scale)   │ + relational│   + job queues     │
│  + code   │           │  state)     │   + sync events)   │
│  + AST)   │           │             │                    │
├───────────┴───────────┴─────────────┴───────────────────┤
│              Continuous Reconciler Daemon                 │
│    (Pieces SQLite reader · filesystem watcher)           │
├─────────────────────────────────────────────────────────┤
│  Sources: Pieces DBs · code repos · documents · photos   │
└─────────────────────────────────────────────────────────┘
```

### What Changes

| Component | v1.0 (current) | v2.0 (hKG) |
|-----------|----------------|-------------|
| Session history | Pieces LTM (local SQLite, read-only) | Neo4j temporal edges + PostgreSQL |
| Entity registry | context.db (local SQLite) | Neo4j nodes with code + AST metadata |
| Search | Keyword FTS on Pieces summaries | Semantic vector search (Qdrant + Neo4j) |
| Embeddings | None | qwen3-embeddings or similar (4096-dim) |
| Cross-machine | None (each machine isolated) | Continuous reconciler syncs Pieces DBs to shared stores |
| Document understanding | None | Cognee + Docling (PDFs, images, scans) |
| Caching | None | Redis (hot query cache, pub/sub) |
| Graph model | Flat tables | General directed graph (cycles = information, not errors) |

### Key Design Decisions

1. **Neo4j nodes carry everything**: source code, vector embeddings, AST structure,
   and temporal narrative — not just references. Each node is a complete
   representation that can be queried from any angle.

2. **General directed graph, not DAG**: both structural dimensions (circular imports,
   recursive types) and temporal dimensions (reverts, decision oscillation, causal
   loops) can cycle. Cycles are information. Depth-bounded traversal at query time.

3. **PostgreSQL as UUID authority**: all entities get a UUID minted in PostgreSQL.
   Neo4j and Qdrant reference by UUID. PostgreSQL also stores the relational state
   equivalent of the current context.db tables.

4. **Continuous reconciliation**: a daemon reads Pieces SQLite databases from each
   machine (read-only), extracts new events, and feeds them through the Cognee
   pipeline into the shared graph. This solves the "Pieces backup is destructive"
   problem — the hKG is the merge layer.

5. **Scope beyond code**: the hKG is designed as an "all-memory" system. Docling
   handles non-code documents (PDFs, DOCX, scanned images). Vision models handle
   photos. The coding session use case is feature one; life-document search is the
   full vision.

### Migration Path

The transition is additive, not destructive:

1. **v1.1** — Add PostgreSQL as an alternative backend for context.db tables
   (session_intents, entity_registry, etc.). SQLite remains the default for
   single-machine installs.

2. **v1.2** — Add Qdrant vector search alongside Pieces FTS. Embed checklist
   items, session intents, and entity descriptions for semantic search.

3. **v1.3** — Add Neo4j for entity relationships. Build the graph from
   entity_registry + git history + AST parsing. Query tools gain graph traversal.

4. **v1.4** — Continuous reconciler daemon. Reads Pieces SQLite from multiple
   machines, deduplicates, and feeds the shared stores. Cross-machine session
   history becomes available.

5. **v2.0** — Cognee integration. Automated entity extraction, relationship
   inference, and RAG pipeline. Docling for document understanding. The server
   becomes a thin MCP query layer over Cognee's graph.

Each version is backward-compatible. The SQLite-only v1.0 continues to work for
users who don't need or want the networked datastores.

### Infrastructure Requirements (for hKG)

The hKG datastores are designed to run as LXC containers on a home server or
equivalent always-on infrastructure:

| Component | Purpose | Resource footprint |
|-----------|---------|-------------------|
| Neo4j | Graph + vectors + AST + code | ~2-4GB RAM |
| Qdrant | Bulk vector scale | ~1-2GB RAM |
| PostgreSQL | UUID authority + relational state | ~512MB RAM |
| Redis | Cache + pub/sub + job queues | ~50MB RAM |
| Reconciler daemon | Pieces sync + Cognee pipeline | ~1GB RAM (during indexing) |

Total: ~5-8GB RAM on the server. The MCP server itself remains lightweight
(runs on developer machines, connects to the shared stores over LAN/VPN).

## Contributing

Contributions welcome. The server is intentionally a single Python file with
stdlib-only dependencies to keep the barrier to entry low. The hKG components
will be separate packages that the server imports conditionally.
