# session-continuity-mcp

> Copyright (C) 2025 Robin L. M. Cheung, MBA. All rights reserved.

**Cross-session AI context protocol — prevents "coding in circles" restarts.**

## The Problem: Circular Programming

Every AI coding session starts with amnesia. The agent doesn't know what the last
session built, what decisions were made, what entities exist, or what's left to do.
So it re-derives everything from scratch — often differently — creating parallel
implementations that diverge from the existing codebase.

This manifests in three recurring failure modes that compound on each other:

### Failure Mode 1: The Interrupted Session

The most destructive scenario. A session partially implements a feature, then gets
interrupted (context compaction, timeout, crash, token limit). The next session
discovers the half-built code, doesn't recognise it as in-progress work, and
**intentionally creates a replacement under a different name**.

```mermaid
flowchart TD
    S1[🟢 Session 1 starts] --> Build["Builds UserAuth in src/auth.ts<br>- Creates class skeleton<br>- Implements 2 of 5 methods<br>- Leaves TODO stubs in the rest"]
    Build --> Interrupt["⚡ Session interrupted<br>(context compaction / token limit / crash)<br><b>No session summary saved</b>"]
    Interrupt --> S2[🟢 Session 2 starts fresh]
    S2 --> Explore["Explores codebase...<br>Finds src/auth.ts"]
    Explore --> Misread["Sees broken UserAuth:<br>- 3 methods throw NotImplementedError<br>- Tests don't pass<br>- No docs explaining it's in-progress"]
    Misread --> Decide{"Agent's conclusion"}
    Decide -->|"Looks like legacy/broken code"| New["Creates AuthService<br>in src/services/auth.ts<br>(a 'proper' replacement)"]
    Decide -->|"Maybe I should fix it?"| Partial["Rewrites 2 methods with<br>different signatures,<br>breaks the 2 that worked"]
    New --> Result1["📁 Codebase now has:<br>- src/auth.ts (partially built, abandoned)<br>- src/services/auth.ts (new, also partial)<br>- Neither is complete<br>- Imports point to the old one"]
    Partial --> Result2["📁 Codebase now has:<br>- src/auth.ts (Frankenstein mix of<br>&nbsp;&nbsp;Session 1 + Session 2 patterns)<br>- 0 of 5 methods actually work<br>- Was closer to done BEFORE Session 2"]

    style Interrupt fill:#8B0000,color:#fff
    style Result1 fill:#4a1942,color:#fff
    style Result2 fill:#4a1942,color:#fff
    style Misread fill:#8B4513,color:#fff
```

The tragedy: Session 1 was **60% done**. After Session 2's "help", it's **0% done
with twice the mess**. And Session 3 will find *two* broken auth implementations
and may well create a third.

### Failure Mode 2: The Shallow Spelunker

AI agents typically search for existing code before implementing. But they have a
systematic bias: **they stop searching after the first match**, even when the
codebase has multiple relevant files. Worse, they often grep for a term, find one
file, and confidently declare they understand the full picture.

```mermaid
flowchart TD
    Start[🟢 New session: 'Implement auth'] --> Search["Searches codebase:<br>grep -r 'auth' src/"]
    Search --> Results["Results:<br>1. src/auth.ts ← finds this first<br>2. lib/auth/index.ts ← doesn't look further<br>3. src/middleware/authGuard.ts ← never sees this<br>4. config/auth.config.ts ← never sees this"]
    Results --> Stop["✋ Stops after first match<br>'Found it! src/auth.ts is the auth module'"]
    Stop --> Read["Reads src/auth.ts<br>(the broken one from Session 1)"]
    Read --> Conclude{"Agent's assessment"}
    Conclude -->|"This looks incomplete"| Create["Creates LoginManager<br>in lib/auth/login.ts<br>(3rd implementation)"]
    Conclude -->|"This is the auth system"| Build["Builds on top of broken stubs,<br>adds features to code that<br>doesn't actually work"]
    Create --> State["📁 Codebase now has:<br>- src/auth.ts (Session 1, broken)<br>- src/services/auth.ts (Session 2, broken)<br>- lib/auth/login.ts (Session 3, ignores the other two)<br>- lib/auth/index.ts (original, still works, never found)<br>- src/middleware/authGuard.ts (imports from... which one?)"]
    Build --> State2["📁 Features added to broken foundation<br>- Looks like progress from git diff<br>- Actually moves further from working state<br>- Tests all mock the broken parts so they 'pass'"]

    style Stop fill:#8B4513,color:#fff
    style State fill:#4a1942,color:#fff
    style State2 fill:#4a1942,color:#fff
```

### Failure Mode 3: The Premature "Ship It!"

Perhaps the most insidious mode. The agent implements a feature with **stubs,
placeholder values, and hardcoded test data**, then confidently declares it
complete and production-ready. If you've ever had an AI assistant tell you
"Done! Fully implemented and ready to ship!" only to find `return true`,
`TODO: implement`, and `API_KEY = "test-key-replace-me"` — you know the feeling.

```mermaid
flowchart TD
    Start[🟢 Session implements auth] --> Code["Writes auth module:<br><code>async verifyToken(token) ‹return true›</code><br><code>const API_URL = 'http://localhost:3000'</code><br><code>// TODO: add rate limiting</code><br><code>// TODO: implement refresh tokens</code>"]
    Code --> Tests["Writes tests:<br><code>jest.mock('./auth')</code><br><code>expect(verifyToken('any')).toBe(true) ✅</code><br>(mocks the function it just wrote)"]
    Tests --> Declare["🎉 'Done! All tests passing!<br>Authentication is fully implemented<br>and production-ready to ship!'"]
    Declare --> Checklist["Marks in CHECKLIST.md:<br>[X] Implement authentication<br>[X] Add token verification<br>[X] Write auth tests<br>All green! ✅✅✅"]
    Checklist --> Next[🟢 Session N+1 starts]
    Next --> Trust["Sees all items marked done ✅<br>'Auth is complete, moving on<br>to build features on top of it'"]
    Trust --> Build["Builds payment system<br>that depends on auth...<br>which returns true for every token...<br>with a localhost URL in prod config...<br>and no rate limiting"]
    Build --> Ship["🚀 Deployed to production<br>with test stubs handling real auth"]

    style Declare fill:#8B4513,color:#fff
    style Ship fill:#8B0000,color:#fff
    style Code fill:#4a1942,color:#fff
```

**What's left in the codebase:**

| What the agent said | What's actually there |
|---------------------|-----------------------|
| "Token verification implemented" | `return true` (accepts every token) |
| "API integration complete" | Hardcoded `localhost:3000` |
| "Rate limiting added" | `// TODO: add rate limiting` |
| "Comprehensive test coverage" | Tests mock the code they're testing |
| "Production-ready!" | One `verifyToken('anything')` away from a breach |

### Why it happens

The root cause is **not** that AI agents are bad at coding. It's that they lack
three pieces of information that humans carry between sessions automatically:

```mermaid
flowchart TD
    Gap["<b>THE INFORMATION GAP</b>"] --> G1["1. What did the last session<br>ACTUALLY do? (vs. what it intended)"]
    Gap --> G2["2. What is the canonical state<br>of the task list RIGHT NOW?"]
    Gap --> G3["3. What named entities exist<br>and WHERE are they?"]
    G1 --> Effects
    G2 --> Effects
    G3 --> Effects
    Effects["<b>WITHOUT THIS, THE AGENT...</b>"] --> E1["Re-explores from scratch"]
    Effects --> E2["Creates new implementations<br>under new names"]
    Effects --> E3["Stops searching after first match"]
    Effects --> E4["Can't distinguish done from<br>broken-and-abandoned"]
    Effects --> E5["Builds on top of stubs,<br>declares 'Ship it!'"]
    E1 --> CP["<b>CIRCULAR PROGRAMMING</b><br>Same work, different results,<br>compounding divergence"]
    E2 --> CP
    E3 --> CP
    E4 --> CP
    E5 --> CP

    style Gap fill:#1a1a2e,color:#e0e0fa,stroke:#7c4dff
    style Effects fill:#1a1a2e,color:#e0e0fa,stroke:#7c4dff
    style CP fill:#8B0000,color:#fff
```

### The compounding effect

Circular programming gets **worse** over time, not better. Each session that starts
without context adds another layer of partial, divergent implementation. The worst
case is a **partially-implemented feature without saved context**: the next session
sees broken stubs and invents new ones alongside them. This is worse than no
implementation at all.

```mermaid
flowchart LR
    subgraph S1["Session 1"]
        A1["Creates UserAuth<br>(60% complete)"]
    end
    subgraph S2["Session 2"]
        A2["Finds broken UserAuth<br>Creates AuthService<br>(40% complete)"]
    end
    subgraph S3["Session 3"]
        A3["Finds two broken auths<br>Creates LoginManager<br>(30% complete)"]
    end
    subgraph S4["Session 4"]
        A4["Finds three broken auths<br>Tries to 'unify' them<br>Breaks all three"]
    end
    subgraph S5["Session 5"]
        A5["🔥 User deletes branch<br>Starts over from scratch"]
    end

    S1 --> S2 --> S3 --> S4 --> S5

    style S1 fill:#1a3a1a,color:#fff
    style S2 fill:#3a3a1a,color:#fff
    style S3 fill:#4a2a1a,color:#fff
    style S4 fill:#5a1a1a,color:#fff
    style S5 fill:#8B0000,color:#fff
```

## The Solution: Session Continuity Protocol

This server gives every AI session **full context in one call**. Instead of exploring
from scratch, the agent receives:

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                    session_briefing() returns:                   │
 ├─────────────────────────────────────────────────────────────────┤
 │                                                                  │
 │  1. PROJECT INDEX (codemap)     Token-efficient structural map   │
 │     (PROJECT_INDEX.md/.json     of the codebase: modules, entry  │
 │      matched pair)              points, dependencies (~3K tokens │
 │                                 vs ~58K for full codebase read)  │
 │                                                                  │
 │  2. RECENT GIT HISTORY         What actually changed on disk     │
 │     (last 10 commits, branch,   (authoritative, not recalled)    │
 │      dirty status)                                               │
 │                                                                  │
 │  3. CHECKLIST STATUS            Single source of truth for       │
 │     (parsed with four-state     what's done, in-progress,        │
 │      markers: [ ] [/] [X] ✅)    pending, blocked                │
 │                                                                  │
 │  4. PRIOR SESSION INTENTS       What other sessions claimed      │
 │     (incomplete intents with    they would do (collision          │
 │      file lists)                detection)                       │
 │                                                                  │
 │  5. SAVED SESSION SUMMARIES     Narrative context: decisions,    │
 │     (from save_session_summary) gotchas, in-progress state       │
 │                                                                  │
 │  6. PIECES LTM HISTORY         OS-level activity capture         │
 │     (optional, from Pieces      (window titles, auto-captured)   │
 │      for Developers)                                             │
 │                                                                  │
 │  7. ENTITY REGISTRY             What functions/classes/types      │
 │     (name → file:line map)      exist and where they live        │
 │                                                                  │
 └─────────────────────────────────────────────────────────────────┘
```

### The reinforcing pipeline

The protocol works through four reinforcing layers. Each layer feeds into the next,
and `session_briefing()` returns all of them at once:

```
 ARCHITECTURE.md ──────► Entity table: what exists, where, signatures
       │                      │
       ▼                      ▼
 CHECKLIST.md ─────────► Tasks cite entities by EXACT NAME
       │                  (no ambiguity, no room for reinterpretation)
       │                      │
       ▼                      ▼
 Entity Registry ──────► register_entity() keeps the map current
       │                  as code changes during implementation
       │                      │
       ▼                      ▼
 Session Summaries ────► save_session_summary() persists decisions,
       │                  gotchas, partially-built state
       │                      │
       ▼                      ▼
 session_briefing() ───► Returns ALL of the above to the next session
       │                      │
       └──────────────────────┘
              CYCLE BROKEN
       (next session starts with full context,
        not from scratch)
```

### Before and after

```
 WITHOUT session-continuity-mcp:        WITH session-continuity-mcp:

 Session N ends                         Session N ends
      │                                      │
      ▼                                      ▼
 Context vanishes                       save_session_summary()
      │                                 complete_session_intent()
      ▼                                      │
 Session N+1 starts                          ▼
      │                                 Session N+1 starts
      ▼                                      │
 "Let me explore                             ▼
  the codebase..."                      session_briefing()
      │                                      │
      ▼                                      ▼
 30 min re-deriving                     "Last session completed P2.1-P2.4,
 what already exists                     registered 3 entities, P2.5 is
      │                                  in-progress with a gotcha about
      ▼                                  the API rate limit. Picking up
 Builds something                        where it left off."
 different                                   │
      │                                      ▼
      ▼                                 Continues seamlessly
 DIVERGENCE                             NO DIVERGENCE
```

### The checkpoint rule

**Any checkpoint without persisted session context is Circular Programming Express.**

If your AI tool auto-saves, compacts context, or checkpoints state, the session
protocol's `save_session_summary()` must also fire. A checkpoint that captures code
state but not session context creates exactly the condition this protocol prevents.

## Current Architecture

session-continuity-mcp currently runs as a **single-file Python server** (stdlib only, no external dependencies) that reads from three data sources:

```
 AI Tool (Claude Code, Windsurf, Roo, Codex, Gemini)
     │
     ▼ MCP stdio (JSON-RPC 2.0)
 ┌────────────────────────────────────────────────┐
 │          session-continuity-mcp                 │
 │          (single Python file, stdlib only)      │
 ├────────────────────────────────────────────────┤
 │                                                 │
 │  context.db (SQLite, read-write)                │
 │  ├─ session_intents      — what each session    │
 │  ├─ session_summaries    — narrative context ◄──┼── PRIMARY persistence
 │  ├─ entity_registry      — name → file:line     │   (Pieces-independent)
 │  ├─ checklist_cache      — status overlay       │
 │  ├─ project_registry     — project → root path  │
 │  └─ project_keywords     — fuzzy matching       │
 │                                                 │
 │  Pieces LTM (SQLite, read-only, OPTIONAL)       │
 │  └─ Reads c2windowTitle + clipboard fields      │
 │     (OS-level capture, bypasses Pieces API)     │
 │                                                 │
 │  git (subprocess, read-only)                    │
 │  └─ log, branch, status, diff                   │
 │                                                 │
 │  CHECKLIST.md (filesystem, read-only parse)     │
 │  └─ Four-state markers: [ ] [/] [X] ✅          │
 │                                                 │
 └────────────────────────────────────────────────┘
```

### Why Pieces is optional (and bypassed for retrieval)

[Pieces for Developers](https://pieces.app) provides valuable **OS-level context
capture** — it records window titles (via the OS window manager API) and clipboard
content (via the OS clipboard API) across every application. These are clean,
high-fidelity signals that land in a local SQLite database.

However, this server **reads the raw SQLite DB directly** rather than going through
Pieces' MCP server or API. Here's why:

| Aspect | Pieces API/MCP | Our direct DB read |
|--------|----------------|-------------------|
| **Capture quality** | Same underlying data | Same underlying data |
| **Retrieval quality** | Depends on inference model + VRAM | Raw field access, no inference |
| **Local inference** | Requires significant VRAM for quality results | N/A — no inference needed |
| **Pricing dependency** | Cloud models limited on free tier, unlimited on Pro ($18.99/mo) | Zero — reads local files |
| **Reliability** | MCP queries can return poor results | Direct SQL, deterministic |

The golden goose is the **capture engine**, not the retrieval layer. By reading
`c2windowTitle` and clipboard fields directly, we get perfect-fidelity session
history without depending on inference quality, VRAM availability, or pricing
tier changes.

**Derisking**: `save_session_summary` provides a fully Pieces-independent
persistence path. Even if Pieces changes their local DB format, gates it behind
a paid tier, or disappears entirely, all core session continuity features
continue to work through context.db alone. The [ROADMAP](ROADMAP.md) details the
planned transition to a self-hosted hybrid Knowledge Graph that replaces Pieces
capture entirely.

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

- **context.db** (read-write, created on first run) — **primary persistence, Pieces-independent**
  - Tables: `session_intents`, `session_summaries`, `entity_registry`, `checklist_cache`, `project_registry`, `project_keywords`
  - `session_summaries` is the main narrative persistence mechanism
- **Pieces LTM** (read-only, optional) — supplementary session history
  - Only reads clean OS-level fields: `c2windowTitle` and clipboard
  - Never uses OCR fields (`c0readable`, `c10 ocrText`) — too noisy
  - Bypasses Pieces API/MCP entirely (direct SQLite read) for reliability
  - Override path with `PIECES_DB_PATH` env var
  - Without Pieces: `get_recent_sessions` and `search_history` return empty; all other tools work normally
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
