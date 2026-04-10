# session-continuity-mcp

> Copyright (C) 2025 Robin L. M. Cheung, MBA. All rights reserved.

Cross-session AI context MCP server — prevents "coding in circles" restarts.

**The problem it solves**: AI sessions start from scratch every time, reimplement things differently, cause within-file divergence, and force the user to restart clean. This server gives every session full context in one call.

## Current Architecture

session-continuity-mcp currently runs as a **single-file Python server** (stdlib only, no external dependencies) that reads from two data sources:

- **Pieces OS LTM** (read-only) — session history from [Pieces for Developers](https://pieces.app). Optional; the server works without it but `get_recent_sessions` and `search_history` return empty results.
- **context.db** (read-write SQLite) — session intents, entity registry, checklist cache, project registry, project keywords. Created automatically on first run.

For the planned evolution to a hybrid Knowledge Graph architecture, see [ROADMAP.md](ROADMAP.md).

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/rebots-online/session-continuity-mcp.git

# 2. Register with your AI tool (see Setup per Tool below)

# 3. Register your project
register_project("my-project", "/path/to/my-project")

# 4. Call session_briefing at the start of every session
session_briefing("my-project")
```

Returns: recent git history, CHECKLIST status (with four-state markers), incomplete prior session intents, Pieces LTM session history, and the named entity registry.

## Requirements

- **Python 3.10+** (stdlib only — no pip install needed)
- **Pieces for Developers** (optional) — for LTM session history integration
- **git** — for repository state queries

## Setup per Tool

Config examples are in the `examples/` directory. Replace `<INSTALL_PATH>` with the actual path to your clone.

### Claude Code

```bash
claude mcp add context-mcp -s user -- python3 <INSTALL_PATH>/session-continuity-mcp/server.py
```

Or add to `~/.claude.json` under `"mcpServers"` — see `examples/claude-code.mcp.json`.

### Windsurf-next

Add to `~/.codeium/windsurf-next/mcp_config.json` — see `examples/windsurf-next.mcp_config.json`.

### Roo Coder (VS Code / VS Code Insiders / VSCodium)

Roo stores MCP config in its globalStorage settings:

- **VS Code**: `~/.config/Visual Studio Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`
- **VS Code Insiders**: `~/.config/Code - Insiders/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`
- **VSCodium**: `~/.config/VSCodium/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`

See `examples/roo-coder.mcp_settings.json`. The `alwaysAllow` list auto-approves read-only tools.

### Codex CLI

Add to `~/.codex/config.toml` — see `examples/codex.config.toml`.

### Gemini CLI

```bash
gemini mcp add -s user context-mcp python3 <INSTALL_PATH>/session-continuity-mcp/server.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PIECES_DB_PATH` | `~/Documents/com.pieces.os/.../db.sqlite3` | Override Pieces OS database location |
| `CONTEXT_DB_PATH` | `<server dir>/context.db` | Override context database location |

## Skills (Claude Code)

Four skills are included for the `/sesh:` command namespace:

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/sesh:briefing` | Session start | Calls `session_briefing`, summarizes context |
| `/sesh:intent` | Before coding | Calls `record_session_intent`, checks for file conflicts |
| `/sesh:save` | Milestones, checkpoints, pre-compaction | Calls `save_session_summary`, persists context |
| `/sesh:done` | Session end | Saves summary, marks checklist items, registers entities, completes intent |

### Install skills

```bash
./install-skills.sh
```

This symlinks `skills/sesh-*` into `~/.claude/skills/`.

### CLAUDE.md integration

Copy `examples/CLAUDE.md.snippet` into any project's `CLAUDE.md` to instruct all AI agents to follow the session protocol.

## Available Tools

| Tool | Purpose |
|------|---------|
| `session_briefing(project_name)` | **PRIMARY** — full context dump for a new session |
| `save_session_summary(project, summary, ...)` | **PERSIST** — save session context before exit or at milestones |
| `get_checklist(project_name)` | Parse CHECKLIST.md into structured items with status |
| `mark_checklist_item(project, text, status, note)` | Update item status |
| `record_session_intent(project, intent, files, session_id)` | Declare what you're doing |
| `complete_session_intent(project, session_id, outcome)` | Mark intent done |
| `get_recent_sessions(project, n)` | Session history from Pieces + recorded intents |
| `get_entity_registry(project, type?)` | Named entity map (what is X and where?) |
| `register_entity(project, name, type, file, line?)` | Add/update an entity |
| `search_history(project, query)` | Search Pieces session summaries |
| `register_project(name, root_path)` | Register a new project |
| `add_project_keyword(project, keyword)` | Add keyword variant for Pieces matching |
| `list_projects()` | List all registered projects |

## Checklist Markers (Four-State System)

The checklist parser recognizes all four states:

| Marker | State | Meaning |
|--------|-------|---------|
| `[ ]` | pending | Defined but not yet begun |
| `[/]` | in_progress | Work has started |
| `[X]` | done | Code written, not yet verified |
| `✅` | verified | Verification command run, output matched acceptance criteria |

Also supported: `[>]` (in_progress), `[~]` (blocked).

## Workflow Protocol

```
1. SESSION START
   └─ session_briefing("my-project")
      → See git history, CHECKLIST, prior intents, saved summaries, entity map

2. BEFORE CODING
   └─ record_session_intent("my-project", "What I will do", files=["..."])
      → Warns if another session claimed the same files

3. DURING WORK
   └─ register_entity() for new functions/classes/endpoints
   └─ mark_checklist_item() as items complete
   └─ save_session_summary() after milestones or when context may be lost

4. SESSION END
   └─ save_session_summary("my-project", "Full structured summary", ...)
   └─ complete_session_intent("my-project", session_id, outcome="...")
      → Always save BEFORE completing intent (summary is critical, intent is nice-to-have)
```

## Anti-Circular-Programming Architecture

The "coding in circles" problem has a specific root cause: a new session lacks the
vocabulary, decisions, and state of previous sessions, so it re-derives everything
from scratch -- often differently. This protocol breaks the cycle with a reinforcing
pipeline:

```
ARCHITECTURE.md          ← Entity table: what exists, where, key signatures
       │
       ▼
CHECKLIST.md             ← Tasks cite entities by exact name (no ambiguity)
       │
       ▼
Entity Registry          ← register_entity() keeps the map current as code changes
       │
       ▼
Session Summaries        ← save_session_summary() persists narrative context
       │
       ▼
session_briefing()       ← Returns ALL of the above to the next session
```

### Why each layer matters

- **Architecture defines the vocabulary.** Entity names, types, file locations,
  and key signatures form a shared language. Without this, two sessions may call
  the same concept by different names and create parallel implementations.

- **Checklist uses that vocabulary.** Each task cites entities by exact name from
  the architecture's entity table. A task that says "implement the thing" without
  specifying which entities, files, and signatures is incomplete -- it leaves room
  for the next session to invent its own interpretation.

- **Entity registry keeps vocabulary current.** As implementation proceeds, entities
  move, get renamed, or gain new signatures. `register_entity()` updates the map so
  the next session doesn't chase stale references.

- **Session summaries capture the narrative.** Decisions made, gotchas discovered,
  partially-implemented features, blocked items. Without this, a partially-built
  feature is *worse* than nothing -- the next session sees broken stubs and invents
  new ones alongside them.

### The checkpoint rule

**Any checkpoint without persisted session context is Circular Programming Express.**

If your AI tool auto-saves, checkpoints, compacts context, or triggers any state
persistence mechanism, the session protocol's `save_session_summary()` must also
fire. A checkpoint that captures code state but not session context creates exactly
the condition this protocol exists to prevent: the next session sees partially-written
code with no record of what was intended, what was decided, or what comes next.

## Data Sources

- **Pieces LTM** (read-only, optional) — session history from Pieces for Developers
  - Only uses clean fields: `c2windowTitle` (OS API) and clipboard (OS API)
  - Never uses OCR fields — too noisy
  - Override path with `PIECES_DB_PATH` env var
- **context.db** (read-write, created on first run)
  - Tables: `session_intents`, `session_summaries`, `entity_registry`, `checklist_cache`, `project_registry`, `project_keywords`
- **git** — authoritative file state (subprocess)
- **CHECKLIST.md** — single source of truth for what needs to be done

## Project Keywords

Each project can have keyword variants for matching Pieces session summaries:

```
add_project_keyword("my-project", "myproj")
add_project_keyword("my-project", "my-proj-v2")
```

Keywords are stored in `project_keywords` table and can be added at runtime or seeded in `DEFAULT_PROJECT_KEYWORDS` in server.py.

## Critical Rule

**Never create a parallel CHECKLIST.** The single `CHECKLIST.md` in git is the only checklist. Two checklists = competing definitions of "done" = forking = divergence.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the planned evolution from local SQLite + Pieces LTM to a hybrid Knowledge Graph (hKG) architecture.

## License

Copyright (C) 2025 Robin L. M. Cheung, MBA. All rights reserved.
See [LICENSE](LICENSE) for details.
