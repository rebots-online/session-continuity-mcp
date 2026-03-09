# context-mcp

> Copyright (C) 2025 Robin L. M. Cheung, MBA. All rights reserved.

Cross-session AI context MCP server — prevents "coding in circles" restarts.

**The problem it solves**: AI sessions start from scratch every time → reimplement things differently → within-file divergence → user must restart clean. This server gives every session full context in one call.

## Quick Start

**Always call `session_briefing` first** at the start of every session in every AI tool.

```
session_briefing("HelloWord")
```

Returns: recent git history, CHECKLIST status, incomplete prior session intents, Pieces session history, named entity registry.

## Setup per Tool

### Claude Code

Add to `~/.claude/mcp.json` (global) or `<project>/.mcp.json` (project-scoped):

```json
{
  "mcpServers": {
    "context": {
      "command": "python3",
      "args": ["/home/robin/Antigravity/tools/context-mcp/server.py"]
    }
  }
}
```

### Windsurf

`~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "context": {
      "command": "python3",
      "args": ["/home/robin/Antigravity/tools/context-mcp/server.py"]
    }
  }
}
```

### VSCode / Roo

`.vscode/mcp.json` in project root:

```json
{
  "servers": {
    "context": {
      "type": "stdio",
      "command": "python3",
      "args": ["/home/robin/Antigravity/tools/context-mcp/server.py"]
    }
  }
}
```

### Gemini CLI / Codex CLI

Add to your tool's MCP config (consult tool docs for exact path):

```json
{
  "mcpServers": {
    "context": {
      "command": "python3",
      "args": ["/home/robin/Antigravity/tools/context-mcp/server.py"]
    }
  }
}
```

## Available Tools

| Tool | Purpose |
|------|---------|
| `session_briefing(project_name)` | **PRIMARY** — full context dump for a new session |
| `get_checklist(project_name)` | Parse CHECKLIST.md → structured items |
| `mark_checklist_item(project, text, status, note)` | Update item status |
| `record_session_intent(project, intent, files, session_id)` | Declare what you're doing |
| `complete_session_intent(project, session_id, outcome)` | Mark intent done |
| `get_recent_sessions(project, n)` | Session history from Pieces + recorded intents |
| `get_entity_registry(project, type?)` | Named entity map (what is X and where?) |
| `register_entity(project, name, type, file, line?)` | Add/update an entity |
| `search_history(project, query)` | Search Pieces session summaries |
| `register_project(name, root_path)` | Register a new project |
| `list_projects()` | List all registered projects |

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

- **Pieces LTM** (`~/Documents/.../Pieces/couchbase.cblite2/db.sqlite3`) — read-only, 21,640+ events
  - Only uses clean fields: `c2windowTitle` (OS API) and clipboard (OS API)
  - Never uses OCR fields — too noisy (character substitutions)
- **context.db** (same directory as server.py) — read-write, mutable state
  - session_intents, entity_registry, checklist_cache, project_registry
- **git** — authoritative file state (subprocess)
- **CHECKLIST.md** — single source of truth for what needs to be done

## Critical Rule

**Never create a parallel CHECKLIST.** The single `CHECKLIST.md` in git is the only checklist. Two checklists = competing definitions of "done" = forking = divergence.
