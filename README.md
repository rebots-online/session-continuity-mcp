# session-continuity-mcp

> Copyright (C) 2025 Robin L. M. Cheung, MBA. All rights reserved.

Cross-session AI context MCP server — prevents "coding in circles" restarts.

**The problem it solves**: AI sessions start from scratch every time, reimplement things differently, cause within-file divergence, and force the user to restart clean. This server gives every session full context in one call.

## Quick Start

**Always call `session_briefing` first** at the start of every session in every AI tool.

```
session_briefing("excallmdraw")
```

Returns: recent git history, CHECKLIST status (with four-state markers), incomplete prior session intents, Pieces LTM session history, and the named entity registry.

## Setup per Tool

Config examples are in the `examples/` directory. The server name is `context-mcp` everywhere.

### Claude Code

```bash
claude mcp add context-mcp -s user -- python3 /home/robin/github/session-continuity-mcp/server.py
```

Or add to `~/.claude.json` under `"mcpServers"`:

```json
{
  "context-mcp": {
    "type": "stdio",
    "command": "python3",
    "args": ["/home/robin/github/session-continuity-mcp/server.py"]
  }
}
```

### Windsurf-next

`~/.codeium/windsurf-next/mcp_config.json`:

```json
{
  "mcpServers": {
    "context-mcp": {
      "command": "python3",
      "args": ["/home/robin/github/session-continuity-mcp/server.py"]
    }
  }
}
```

### Roo Coder (VS Code / VS Code Insiders)

Roo stores MCP config in its globalStorage settings:

- **VS Code**: `~/.config/Visual Studio Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`
- **VS Code Insiders**: `~/.config/Code - Insiders/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`
- **VSCodium**: `~/.config/VSCodium/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`

Add to the `"mcpServers"` object:

```json
{
  "context-mcp": {
    "command": "python3",
    "args": ["/home/robin/github/session-continuity-mcp/server.py"],
    "alwaysAllow": [
      "session_briefing", "get_checklist", "list_projects",
      "get_entity_registry", "search_history", "get_recent_sessions"
    ]
  }
}
```

### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.context-mcp]
enabled = true
command = "python3"
args = ["/home/robin/github/session-continuity-mcp/server.py"]
```

### Gemini CLI

```bash
gemini mcp add -s user context-mcp python3 /home/robin/github/session-continuity-mcp/server.py
```

## Skills (Claude Code)

Three skills are included for the `/sesh:` command namespace:

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/sesh:briefing` | Session start | Calls `session_briefing`, summarizes context |
| `/sesh:intent` | Before coding | Calls `record_session_intent`, checks for file conflicts |
| `/sesh:done` | Session end | Marks checklist items, registers entities, completes intent |

### Install skills

```bash
./install-skills.sh
```

This symlinks `skills/sesh-*` into `~/.claude/skills/` so they're available in every Claude Code session.

### CLAUDE.md integration

Copy `examples/CLAUDE.md.snippet` into any project's `CLAUDE.md` to instruct all AI agents to follow the session protocol.

## Available Tools

| Tool | Purpose |
|------|---------|
| `session_briefing(project_name)` | **PRIMARY** — full context dump for a new session |
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

The checklist parser recognizes all four states from the CLAUDE.md convention:

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
   └─ session_briefing("ProjectName")
      → See git history, CHECKLIST, prior intents, entity map

2. BEFORE CODING
   └─ record_session_intent("ProjectName", "What I will do", files=["..."])
      → Warns if another session claimed the same files

3. DURING WORK
   └─ register_entity() for new functions/classes/endpoints
   └─ mark_checklist_item() as items complete

4. SESSION END
   └─ complete_session_intent("ProjectName", session_id, outcome="...")
```

## Data Sources

- **Pieces LTM** (`~/Documents/.../Pieces/couchbase.cblite2/db.sqlite3`) — read-only
  - Only uses clean fields: `c2windowTitle` (OS API) and clipboard (OS API)
  - Never uses OCR fields — too noisy (character substitutions)
- **context.db** (same directory as server.py) — read-write, created on first run
  - Tables: `session_intents`, `entity_registry`, `checklist_cache`, `project_registry`, `project_keywords`
- **git** — authoritative file state (subprocess)
- **CHECKLIST.md** — single source of truth for what needs to be done

## Project Keywords

Each project can have keyword variants for matching Pieces session summaries. Keywords are stored in the `project_keywords` table and can be added at runtime:

```
add_project_keyword("excallmdraw", "exa-llm-draw")
```

Default keywords are seeded on first run. Use this when a project has alternate names, abbreviations, or prior iterations that appear in Pieces history.

## Critical Rule

**Never create a parallel CHECKLIST.** The single `CHECKLIST.md` in git is the only checklist. Two checklists = competing definitions of "done" = forking = divergence.
