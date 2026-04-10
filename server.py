#!/usr/bin/env python3
# Copyright (c) 2025 Robin L. M. Cheung, MBA. MIT License — see LICENSE.
"""
session-continuity-mcp/server.py — MCP stdio server for cross-session AI context

Solves the "coding in circles" restart problem: every AI session in every
tool calls session_briefing() first and gets complete context in one call.

Transport: stdio JSON-RPC 2.0 (MCP protocol)
Dependencies: stdlib only — json, sqlite3, subprocess, os, sys, re, datetime, pathlib

Usage:
    python3 /path/to/session-continuity-mcp/server.py

Environment variables:
    PIECES_DB_PATH  — Override the default Pieces OS database path
    CONTEXT_DB_PATH — Override the default context.db location (default: alongside server.py)

Add to .mcp.json / mcp_config.json for your tool (see README.md).
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

TOOLS_DIR    = Path(__file__).parent
CONTEXT_DB   = Path(os.environ.get("CONTEXT_DB_PATH", str(TOOLS_DIR / "context.db")))
PIECES_DB    = Path(os.environ.get("PIECES_DB_PATH",
    str(Path.home() / "Documents/com.pieces.os/production/Pieces/couchbase.cblite2/db.sqlite3")))

# Pieces FTS tables (backslash table names — must use Python sqlite3, not CLI)
EVENTS_FTS   = r"kv_.workstream\Events::workstream\Events\Full\Text\Search\Index_content"
SUMMARIES_FTS = r"kv_.workstream\Summaries::workstream\Summaries\Full\Text\Search\Index_content"

# Known project roots — add your own projects here or use register_project() at runtime.
# Projects are also persisted in context.db so runtime registrations survive restarts.
# Example:
#   "my-project": Path.home() / "code/my-project",
DEFAULT_PROJECT_ROOTS: dict[str, Path] = {}

# Default project keyword variants — seeded into project_keywords table on init.
# Keywords are used to match Pieces LTM session summaries to projects.
# Add your own or use add_project_keyword() at runtime.
# Example:
#   "my-project": ["myproj", "my project", "mp"],
DEFAULT_PROJECT_KEYWORDS: dict[str, list[str]] = {}

# ── DB init ────────────────────────────────────────────────────────────────────

def init_context_db(db: sqlite3.Connection) -> None:
    """Create tables if they don't exist (idempotent migrations)."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS session_intents (
            id           INTEGER PRIMARY KEY,
            project      TEXT    NOT NULL,
            session_id   TEXT,
            intent       TEXT    NOT NULL,
            files_to_touch TEXT,          -- JSON array of file paths
            started_at   TEXT    NOT NULL,
            completed_at TEXT,
            outcome      TEXT
        );

        CREATE TABLE IF NOT EXISTS entity_registry (
            id          INTEGER PRIMARY KEY,
            project     TEXT NOT NULL,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL,  -- function|class|interface|type|constant|endpoint|table
            file        TEXT NOT NULL,
            line        INTEGER,
            last_seen   TEXT,
            UNIQUE(project, name, type)
        );

        CREATE TABLE IF NOT EXISTS checklist_cache (
            project    TEXT NOT NULL,
            item_id    TEXT NOT NULL,
            status     TEXT DEFAULT 'pending',  -- pending|in_progress|done|blocked
            note       TEXT,
            updated_at TEXT,
            PRIMARY KEY (project, item_id)
        );

        CREATE TABLE IF NOT EXISTS project_registry (
            name       TEXT PRIMARY KEY,
            root_path  TEXT NOT NULL,
            added_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_keywords (
            project  TEXT NOT NULL,
            keyword  TEXT NOT NULL,
            PRIMARY KEY (project, keyword)
        );

        CREATE TABLE IF NOT EXISTS session_summaries (
            id           INTEGER PRIMARY KEY,
            project      TEXT    NOT NULL,
            session_id   TEXT,
            summary      TEXT    NOT NULL,
            files_changed TEXT,          -- JSON array
            entities_registered TEXT,    -- JSON array
            checklist_progress TEXT,     -- JSON: {done: N, in_progress: N, ...}
            saved_at     TEXT    NOT NULL
        );
    """)
    # Seed known projects
    now = _now()
    for name, path in DEFAULT_PROJECT_ROOTS.items():
        db.execute(
            "INSERT OR IGNORE INTO project_registry (name, root_path, added_at) VALUES (?,?,?)",
            (name, str(path), now)
        )
    # Seed project keyword variants
    for project, keywords in DEFAULT_PROJECT_KEYWORDS.items():
        for kw in keywords:
            db.execute(
                "INSERT OR IGNORE INTO project_keywords (project, keyword) VALUES (?,?)",
                (project, kw)
            )
    db.commit()


def open_context_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(CONTEXT_DB))
    db.row_factory = sqlite3.Row
    init_context_db(db)
    return db


def open_pieces_db():
    """Open Pieces DB read-only. Returns None if not available."""
    if not PIECES_DB.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{PIECES_DB}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db
    except Exception:
        return None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root(project_name: str, ctx_db: sqlite3.Connection) -> Path | None:
    row = ctx_db.execute(
        "SELECT root_path FROM project_registry WHERE name = ?", (project_name,)
    ).fetchone()
    if row:
        return Path(row["root_path"])
    # Fuzzy match
    rows = ctx_db.execute("SELECT name, root_path FROM project_registry").fetchall()
    proj_lower = project_name.lower()
    for r in rows:
        if proj_lower in r["name"].lower() or r["name"].lower() in proj_lower:
            return Path(r["root_path"])
    return None


def _git(project_root: Path, *args: str) -> str:
    """Run a git command in project_root, return stdout or empty string on error."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root)] + list(args),
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _parse_checklist(root: Path) -> list[dict]:
    """
    Parse CHECKLIST.md → list of {id, section, text, status, raw_line}.
    status: 'done' | 'pending' | 'in_progress' | 'blocked'
    """
    checklist_path = root / "CHECKLIST.md"
    if not checklist_path.exists():
        return []

    items = []
    section = "General"
    item_idx = 0

    with open(checklist_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip()
            # Section header
            if line.startswith("#"):
                section = line.lstrip("#").strip()
                continue
            # Checkbox line — supports [ ] [x] [X] [~] [>] [/] markers
            m = re.match(r"^\s*[-*]\s+\[([ xX~>/])\]\s+(.*)", line)
            if m:
                marker = m.group(1)
                text = m.group(2).strip()
                if marker in ("x", "X"):
                    status = "done"
                elif marker == "~":
                    status = "blocked"
                elif marker in (">", "/"):
                    status = "in_progress"
                else:
                    status = "pending"
                item_idx += 1
                items.append({
                    "id": f"{section[:20].replace(' ','_')}_{item_idx}",
                    "section": section,
                    "text": text,
                    "status": status,
                    "raw_line": line,
                })
            # ✅ prefix lines — verified/tested state (per CLAUDE.md four-state system)
            elif line.strip().startswith("✅"):
                text = re.sub(r"^✅\s*", "", line.strip())
                if text:
                    item_idx += 1
                    items.append({
                        "id": f"{section[:20].replace(' ','_')}_{item_idx}",
                        "section": section,
                        "text": text,
                        "status": "verified",
                        "raw_line": line,
                    })

    return items


def _pieces_recent_sessions(project_name: str, n: int = 5) -> list[dict]:
    """
    Query Pieces for recent sessions involving this project.
    Uses window titles (clean, reliable) to filter events by project.
    Returns list of {date, summary_name, event_count}.
    """
    pieces_db = open_pieces_db()
    if not pieces_db:
        return []

    sessions = []
    try:
        # Get recent summary names that mention the project
        summ_rows = pieces_db.execute(
            f'SELECT docid, c0name FROM "{SUMMARIES_FTS}" ORDER BY docid DESC LIMIT 50'
        ).fetchall()

        proj_lower = project_name.lower()
        for row in summ_rows:
            name = row["c0name"] or ""
            if proj_lower in name.lower() or _project_keywords(project_name, name):
                sessions.append({
                    "date": "recent",
                    "summary_name": name,
                    "source": "pieces_summary",
                })
                if len(sessions) >= n:
                    break

        # If not enough summaries, fall back to event window title clusters
        if len(sessions) < n:
            event_rows = pieces_db.execute(
                f'SELECT docid, c2windowTitle FROM "{EVENTS_FTS}"'
                f' WHERE c2windowTitle LIKE ? ORDER BY docid DESC LIMIT 500',
                (f"%{project_name}%",)
            ).fetchall()

            # Cluster by approximate "session" (gap of >100 docids = new session)
            clusters = []
            if event_rows:
                cluster_start = event_rows[0]["docid"]
                cluster_count = 1
                prev_docid = event_rows[0]["docid"]
                for r in event_rows[1:]:
                    if prev_docid - r["docid"] > 100:
                        clusters.append({
                            "date": "unknown",
                            "summary_name": f"Session cluster ({cluster_count} events, last docid {prev_docid})",
                            "source": "pieces_events",
                        })
                        cluster_start = r["docid"]
                        cluster_count = 1
                    else:
                        cluster_count += 1
                    prev_docid = r["docid"]
                if cluster_count > 5:
                    clusters.append({
                        "date": "unknown",
                        "summary_name": f"Session cluster ({cluster_count} events, docids {prev_docid}..{cluster_start})",
                        "source": "pieces_events",
                    })
                sessions.extend(clusters[: n - len(sessions)])

    except Exception as e:
        sessions.append({"date": "error", "summary_name": f"Pieces query error: {e}", "source": "error"})
    finally:
        pieces_db.close()

    return sessions[:n]


def _project_keywords(project_name: str, text: str) -> bool:
    """Loose keyword match for project name variants (database-driven)."""
    ctx_db = open_context_db()
    rows = ctx_db.execute(
        "SELECT keyword FROM project_keywords WHERE project = ?",
        (project_name,)
    ).fetchall()
    ctx_db.close()
    text_lower = text.lower()
    return any(row["keyword"] in text_lower for row in rows)


def _pieces_search_summaries(project_name: str, query: str) -> list[dict]:
    """Search Pieces summary names (FTS only has title, not full body)."""
    pieces_db = open_pieces_db()
    if not pieces_db:
        return []
    results = []
    try:
        rows = pieces_db.execute(
            f'SELECT docid, c0name FROM "{SUMMARIES_FTS}" ORDER BY docid DESC LIMIT 200'
        ).fetchall()
        q_lower = query.lower()
        proj_lower = project_name.lower()
        for row in rows:
            name = row["c0name"] or ""
            if q_lower in name.lower() and (proj_lower in name.lower() or _project_keywords(project_name, name)):
                results.append({
                    "docid": row["docid"],
                    "summary_text": name,
                    "relevance": "title_match",
                })
    except Exception as e:
        results.append({"docid": -1, "summary_text": f"Search error: {e}", "relevance": "error"})
    finally:
        pieces_db.close()
    return results


# ── Tool implementations ───────────────────────────────────────────────────────

def tool_session_briefing(project_name: str) -> str:
    """
    PRIMARY TOOL — Returns everything a new session needs to avoid starting from scratch.
    Call this FIRST at the start of every session in every AI tool.
    """
    ctx_db = open_context_db()
    root = _project_root(project_name, ctx_db)

    lines = [f"# Session Briefing: {project_name}", f"Generated: {_now()}", ""]

    # ── 1. Project root ──
    if root:
        lines.append(f"**Project root**: `{root}`")
        lines.append(f"**Exists on disk**: {'✅' if root.exists() else '❌ NOT FOUND'}")
    else:
        lines.append(f"⚠️ Project '{project_name}' not in registry. Use register_project tool.")
    lines.append("")

    # ── 2. Recent git log ──
    lines.append("## Recent Git History (last 10 commits)")
    if root and root.exists():
        log = _git(root, "log", "--oneline", "-10")
        lines.append("```")
        lines.append(log if log else "(no commits or not a git repo)")
        lines.append("```")
        # Current branch + dirty status
        branch = _git(root, "branch", "--show-current")
        status = _git(root, "status", "--short")
        lines.append(f"**Branch**: `{branch or 'unknown'}`")
        if status:
            lines.append(f"**Uncommitted changes**:\n```\n{status[:600]}\n```")
        else:
            lines.append("**Working tree**: clean")
    else:
        lines.append("_(project root not found)_")
    lines.append("")

    # ── 3. CHECKLIST — in-progress and pending ──
    lines.append("## CHECKLIST Status (single source of truth)")
    checklist_items = []
    if root and root.exists():
        checklist_items = _parse_checklist(root)
    if checklist_items:
        pending   = [i for i in checklist_items if i["status"] == "pending"]
        in_prog   = [i for i in checklist_items if i["status"] == "in_progress"]
        blocked   = [i for i in checklist_items if i["status"] == "blocked"]
        done      = [i for i in checklist_items if i["status"] == "done"]
        verified  = [i for i in checklist_items if i["status"] == "verified"]
        lines.append(f"**Total**: {len(checklist_items)} items | ✅ {len(verified)} verified | ☑️ {len(done)} done | 🔄 {len(in_prog)} in-progress | 🚧 {len(blocked)} blocked | ⏳ {len(pending)} pending")
        lines.append("")
        if in_prog:
            lines.append("### 🔄 In Progress")
            for i in in_prog:
                lines.append(f"- [{i['section']}] {i['text']}")
        if blocked:
            lines.append("### 🚧 Blocked")
            for i in blocked:
                lines.append(f"- [{i['section']}] {i['text']}")
        if pending:
            lines.append(f"### ⏳ Pending ({len(pending)} items)")
            for i in pending[:15]:  # cap at 15 to keep response focused
                lines.append(f"- [{i['section']}] {i['text']}")
            if len(pending) > 15:
                lines.append(f"- _(... {len(pending)-15} more — call get_checklist for full list)_")
    else:
        lines.append("_(no CHECKLIST.md found or no checkbox items)_")
    lines.append("")

    # ── 4. Uncompleted session intents from previous sessions ──
    lines.append("## Previous Session Intents (incomplete)")
    intents = ctx_db.execute(
        "SELECT session_id, intent, files_to_touch, started_at FROM session_intents "
        "WHERE project = ? AND completed_at IS NULL ORDER BY started_at DESC LIMIT 5",
        (project_name,)
    ).fetchall()
    if intents:
        for row in intents:
            lines.append(f"- **[{row['started_at'][:10]}]** {row['intent']}")
            if row["files_to_touch"]:
                try:
                    files = json.loads(row["files_to_touch"])
                    lines.append(f"  Files: {', '.join(files[:5])}")
                except Exception:
                    pass
    else:
        lines.append("_(no incomplete session intents recorded)_")
    lines.append("")

    # ── 5. Recent Pieces session history ──
    lines.append("## Recent Session History (from Pieces LTM)")
    sessions = _pieces_recent_sessions(project_name, n=5)
    if sessions:
        for s in sessions:
            lines.append(f"- {s['summary_name']}")
    else:
        lines.append("_(Pieces DB unavailable or no sessions found)_")
    lines.append("")

    # ── 5b. Saved session summaries (from context.db) ──
    lines.append("## Saved Session Summaries")
    summaries = ctx_db.execute(
        "SELECT session_id, summary, files_changed, checklist_progress, saved_at "
        "FROM session_summaries WHERE project = ? ORDER BY saved_at DESC LIMIT 5",
        (project_name,)
    ).fetchall()
    if summaries:
        for s in summaries:
            lines.append(f"### [{s['saved_at'][:16]}] {s['session_id'] or 'unnamed'}")
            lines.append(s["summary"][:800])
            if s["files_changed"]:
                try:
                    files = json.loads(s["files_changed"])
                    if files:
                        lines.append(f"  Files: {', '.join(files[:10])}")
                except Exception:
                    pass
            if s["checklist_progress"]:
                try:
                    cp = json.loads(s["checklist_progress"])
                    parts = [f"{k}: {v}" for k, v in cp.items() if v]
                    if parts:
                        lines.append(f"  Progress: {', '.join(parts)}")
                except Exception:
                    pass
            lines.append("")
    else:
        lines.append("_(no saved session summaries — use save_session_summary to persist context)_")
    lines.append("")

    # ── 6. Entity registry summary ──
    lines.append("## Named Entity Registry")
    entities = ctx_db.execute(
        "SELECT name, type, file, line FROM entity_registry WHERE project = ? "
        "ORDER BY type, name LIMIT 40",
        (project_name,)
    ).fetchall()
    if entities:
        by_type: dict[str, list] = {}
        for e in entities:
            by_type.setdefault(e["type"], []).append(e)
        for etype, elist in sorted(by_type.items()):
            lines.append(f"**{etype}** ({len(elist)}):")
            for e in elist[:10]:
                loc = f"`{e['file']}`"
                if e["line"]:
                    loc += f":{e['line']}"
                lines.append(f"  - `{e['name']}` → {loc}")
            if len(elist) > 10:
                lines.append(f"  _(... {len(elist)-10} more — call get_entity_registry)_")
    else:
        lines.append("_(no entities registered yet — call register_entity as you work)_")
    lines.append("")

    # ── 7. Key reminders ──
    lines.append("## Key Reminders")
    lines.append("- **Single CHECKLIST rule**: CHECKLIST.md in git is the ONLY checklist. Never create a parallel one.")
    lines.append("- **Record your intent**: Call `record_session_intent` before coding to prevent collisions.")
    lines.append("- **Register entities**: Call `register_entity` after creating/moving functions/classes.")
    lines.append("- **Mark checklist items**: Call `mark_checklist_item` as you complete work.")
    lines.append("- **Save before exit**: Call `save_session_summary` before ending, after milestones, or when context may be lost (compaction, checkpoint).")

    ctx_db.close()
    return "\n".join(lines)


def tool_get_checklist(project_name: str) -> str:
    ctx_db = open_context_db()
    root = _project_root(project_name, ctx_db)
    ctx_db.close()

    if not root or not root.exists():
        return json.dumps({"error": f"Project root not found for '{project_name}'"})

    items = _parse_checklist(root)
    if not items:
        return json.dumps({"error": "No CHECKLIST.md found or no checkbox items", "path": str(root / "CHECKLIST.md")})

    # Build structured output
    result = {
        "project": project_name,
        "checklist_path": str(root / "CHECKLIST.md"),
        "total": len(items),
        "by_status": {
            "verified":    [i for i in items if i["status"] == "verified"],
            "done":        [i for i in items if i["status"] == "done"],
            "in_progress": [i for i in items if i["status"] == "in_progress"],
            "blocked":     [i for i in items if i["status"] == "blocked"],
            "pending":     [i for i in items if i["status"] == "pending"],
        },
        "items": items,
    }
    # Drop raw_line from top-level items array to save tokens
    for it in result["items"]:
        del it["raw_line"]
    return json.dumps(result, indent=2)


def tool_mark_checklist_item(project_name: str, item_text: str, status: str, note: str = "") -> str:
    valid_statuses = {"pending", "in_progress", "done", "blocked", "verified"}
    if status not in valid_statuses:
        return json.dumps({"error": f"Invalid status '{status}'. Must be one of: {sorted(valid_statuses)}"})

    item_id = re.sub(r"[^\w\s]", "", item_text)[:40].strip().replace(" ", "_")

    ctx_db = open_context_db()
    ctx_db.execute(
        """INSERT INTO checklist_cache (project, item_id, status, note, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(project, item_id) DO UPDATE SET
             status=excluded.status, note=excluded.note, updated_at=excluded.updated_at""",
        (project_name, item_id, status, note, _now())
    )
    ctx_db.commit()
    ctx_db.close()

    return json.dumps({
        "ok": True,
        "project": project_name,
        "item_id": item_id,
        "item_text": item_text,
        "status": status,
        "note": note,
        "updated_at": _now(),
        "reminder": "Also update CHECKLIST.md directly — this cache is supplementary.",
    })


def tool_record_session_intent(
    project_name: str,
    intent: str,
    files_to_touch: list[str] | None = None,
    session_id: str | None = None,
) -> str:
    ctx_db = open_context_db()
    files_json = json.dumps(files_to_touch) if files_to_touch else None
    sid = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    ctx_db.execute(
        """INSERT INTO session_intents (project, session_id, intent, files_to_touch, started_at)
           VALUES (?, ?, ?, ?, ?)""",
        (project_name, sid, intent, files_json, _now())
    )
    ctx_db.commit()

    # Warn if any of the files_to_touch are already claimed by an open intent
    warnings = []
    if files_to_touch:
        open_intents = ctx_db.execute(
            "SELECT session_id, intent, files_to_touch FROM session_intents "
            "WHERE project = ? AND completed_at IS NULL AND session_id != ?",
            (project_name, sid)
        ).fetchall()
        for oi in open_intents:
            if oi["files_to_touch"]:
                try:
                    other_files = set(json.loads(oi["files_to_touch"]))
                    overlap = set(files_to_touch) & other_files
                    if overlap:
                        warnings.append(
                            f"⚠️ File conflict with session '{oi['session_id']}' "
                            f"(intent: {oi['intent'][:60]}): {list(overlap)}"
                        )
                except Exception:
                    pass

    ctx_db.close()
    return json.dumps({
        "ok": True,
        "session_id": sid,
        "project": project_name,
        "intent": intent,
        "files_to_touch": files_to_touch or [],
        "warnings": warnings,
        "tip": f"When done, call complete_session_intent with session_id='{sid}'",
    })


def tool_complete_session_intent(project_name: str, session_id: str, outcome: str = "") -> str:
    ctx_db = open_context_db()
    ctx_db.execute(
        "UPDATE session_intents SET completed_at=?, outcome=? WHERE project=? AND session_id=?",
        (_now(), outcome, project_name, session_id)
    )
    rows_affected = ctx_db.execute("SELECT changes()").fetchone()[0]
    ctx_db.commit()
    ctx_db.close()
    if rows_affected == 0:
        return json.dumps({"error": f"No session intent found for session_id='{session_id}' in project='{project_name}'"})
    return json.dumps({"ok": True, "session_id": session_id, "outcome": outcome})


def tool_get_recent_sessions(project_name: str, n: int = 5) -> str:
    sessions = _pieces_recent_sessions(project_name, n=n)
    ctx_db = open_context_db()
    # Add context.db session intents
    intents = ctx_db.execute(
        "SELECT session_id, intent, started_at, completed_at, outcome FROM session_intents "
        "WHERE project = ? ORDER BY started_at DESC LIMIT ?",
        (project_name, n)
    ).fetchall()
    ctx_db.close()

    result = {
        "project": project_name,
        "pieces_sessions": sessions,
        "recorded_intents": [
            {
                "session_id": r["session_id"],
                "intent": r["intent"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
                "outcome": r["outcome"],
                "status": "completed" if r["completed_at"] else "incomplete",
            }
            for r in intents
        ],
    }
    return json.dumps(result, indent=2)


def tool_get_entity_registry(project_name: str, entity_type: str | None = None) -> str:
    ctx_db = open_context_db()
    if entity_type:
        rows = ctx_db.execute(
            "SELECT name, type, file, line, last_seen FROM entity_registry "
            "WHERE project = ? AND type = ? ORDER BY type, name",
            (project_name, entity_type)
        ).fetchall()
    else:
        rows = ctx_db.execute(
            "SELECT name, type, file, line, last_seen FROM entity_registry "
            "WHERE project = ? ORDER BY type, name",
            (project_name,)
        ).fetchall()
    ctx_db.close()

    entities = [
        {"name": r["name"], "type": r["type"], "file": r["file"],
         "line": r["line"], "last_seen": r["last_seen"]}
        for r in rows
    ]
    return json.dumps({
        "project": project_name,
        "filter_type": entity_type,
        "count": len(entities),
        "entities": entities,
    }, indent=2)


def tool_register_entity(
    project_name: str,
    name: str,
    entity_type: str,
    file: str,
    line: int | None = None,
) -> str:
    valid_types = {"function", "class", "interface", "type", "constant", "endpoint", "table"}
    if entity_type not in valid_types:
        return json.dumps({"error": f"Invalid type '{entity_type}'. Must be one of: {sorted(valid_types)}"})

    ctx_db = open_context_db()
    ctx_db.execute(
        """INSERT INTO entity_registry (project, name, type, file, line, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(project, name, type) DO UPDATE SET
             file=excluded.file, line=excluded.line, last_seen=excluded.last_seen""",
        (project_name, name, entity_type, file, line, _now())
    )
    ctx_db.commit()
    ctx_db.close()
    return json.dumps({
        "ok": True,
        "project": project_name,
        "name": name,
        "type": entity_type,
        "file": file,
        "line": line,
    })


def tool_search_history(project_name: str, query: str) -> str:
    results = _pieces_search_summaries(project_name, query)
    note = "" if results else "No Pieces summaries matched. Pieces DB may be unavailable or no matching summaries."
    return json.dumps({
        "project": project_name,
        "query": query,
        "count": len(results),
        "results": results,
        **({"note": note} if note else {}),
    }, indent=2)


def tool_register_project(project_name: str, root_path: str) -> str:
    ctx_db = open_context_db()
    ctx_db.execute(
        """INSERT INTO project_registry (name, root_path, added_at)
           VALUES (?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET root_path=excluded.root_path""",
        (project_name, root_path, _now())
    )
    ctx_db.commit()
    ctx_db.close()
    return json.dumps({
        "ok": True,
        "project": project_name,
        "root_path": root_path,
    })


def tool_add_project_keyword(project_name: str, keyword: str) -> str:
    """Add a keyword variant for a project (used for Pieces session matching)."""
    ctx_db = open_context_db()
    ctx_db.execute(
        "INSERT OR IGNORE INTO project_keywords (project, keyword) VALUES (?,?)",
        (project_name, keyword.lower())
    )
    ctx_db.commit()
    # Return all keywords for this project
    rows = ctx_db.execute(
        "SELECT keyword FROM project_keywords WHERE project = ?",
        (project_name,)
    ).fetchall()
    ctx_db.close()
    return json.dumps({
        "ok": True,
        "project": project_name,
        "keyword_added": keyword.lower(),
        "all_keywords": [r["keyword"] for r in rows],
    })


def tool_save_session_summary(
    project_name: str,
    summary: str,
    files_changed: list[str] | None = None,
    entities_registered: list[str] | None = None,
    checklist_progress: dict | None = None,
    session_id: str | None = None,
) -> str:
    """Save a structured session summary to context.db.
    This is the primary persistence mechanism for session context when Pieces LTM
    is not available. Call this before ending a session or when context may be lost."""
    ctx_db = open_context_db()
    sid = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ctx_db.execute(
        """INSERT INTO session_summaries
           (project, session_id, summary, files_changed, entities_registered,
            checklist_progress, saved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            project_name,
            sid,
            summary,
            json.dumps(files_changed) if files_changed else None,
            json.dumps(entities_registered) if entities_registered else None,
            json.dumps(checklist_progress) if checklist_progress else None,
            _now(),
        )
    )
    ctx_db.commit()
    ctx_db.close()
    return json.dumps({
        "ok": True,
        "project": project_name,
        "session_id": sid,
        "summary_length": len(summary),
        "saved_at": _now(),
    })


def tool_list_projects() -> str:
    ctx_db = open_context_db()
    rows = ctx_db.execute(
        "SELECT name, root_path FROM project_registry ORDER BY name"
    ).fetchall()
    ctx_db.close()
    return json.dumps({
        "projects": [
            {"name": r["name"], "root_path": r["root_path"],
             "exists": os.path.isdir(r["root_path"])}
            for r in rows
        ]
    }, indent=2)


# ── MCP Protocol ───────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "session_briefing",
        "description": (
            "PRIMARY TOOL — Call this FIRST at the start of every session. "
            "Returns full context: recent git history, CHECKLIST status (pending/in-progress), "
            "incomplete session intents from prior sessions, recent Pieces history, and "
            "named entity registry. Prevents coding-in-circles and within-file divergence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Project name (as registered with register_project)"
                }
            },
            "required": ["project_name"]
        },
    },
    {
        "name": "get_checklist",
        "description": (
            "Returns CHECKLIST.md parsed into structured items with status. "
            "This is the single source of truth for what needs to be done. "
            "NEVER create a parallel checklist."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Project name"}
            },
            "required": ["project_name"]
        },
    },
    {
        "name": "mark_checklist_item",
        "description": "Mark a checklist item with a new status. Also update CHECKLIST.md directly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "item_text":    {"type": "string", "description": "Text of the checklist item"},
                "status":       {"type": "string", "enum": ["pending", "in_progress", "done", "blocked", "verified"]},
                "note":         {"type": "string", "description": "Optional note about the status change"},
            },
            "required": ["project_name", "item_text", "status"]
        },
    },
    {
        "name": "record_session_intent",
        "description": (
            "Record what this session intends to do BEFORE starting to code. "
            "Warns if other sessions have claimed the same files. "
            "Call complete_session_intent when done."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name":   {"type": "string"},
                "intent":         {"type": "string", "description": "What this session will do"},
                "files_to_touch": {
                    "type": "array", "items": {"type": "string"},
                    "description": "File paths this session will modify"
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session identifier (auto-generated if omitted)"
                },
            },
            "required": ["project_name", "intent"]
        },
    },
    {
        "name": "complete_session_intent",
        "description": "Mark a previously recorded session intent as completed with an outcome note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "session_id":   {"type": "string", "description": "session_id from record_session_intent"},
                "outcome":      {"type": "string", "description": "What was accomplished"},
            },
            "required": ["project_name", "session_id"]
        },
    },
    {
        "name": "get_recent_sessions",
        "description": "Get recent session history for a project from Pieces LTM and recorded intents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "n": {"type": "integer", "description": "Number of sessions to return (default 5)", "default": 5},
            },
            "required": ["project_name"]
        },
    },
    {
        "name": "get_entity_registry",
        "description": (
            "Return all named entities (functions, classes, interfaces, endpoints, tables) "
            "and their canonical file locations. Use to find 'what is X and where is it?'"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "entity_type": {
                    "type": "string",
                    "enum": ["function", "class", "interface", "type", "constant", "endpoint", "table"],
                    "description": "Filter by entity type (optional)"
                },
            },
            "required": ["project_name"]
        },
    },
    {
        "name": "register_entity",
        "description": (
            "Register a named entity (function, class, endpoint, etc.) with its canonical file location. "
            "Call after creating or moving important named things."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "name":         {"type": "string", "description": "Entity name (e.g., 'CalendarEngine', 'session_briefing')"},
                "entity_type":  {
                    "type": "string",
                    "enum": ["function", "class", "interface", "type", "constant", "endpoint", "table"]
                },
                "file":         {"type": "string", "description": "File path (relative or absolute)"},
                "line":         {"type": "integer", "description": "Line number (optional)"},
            },
            "required": ["project_name", "name", "entity_type", "file"]
        },
    },
    {
        "name": "search_history",
        "description": "Search Pieces LTM session summaries for this project matching a query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "query":        {"type": "string", "description": "Search query"},
            },
            "required": ["project_name", "query"]
        },
    },
    {
        "name": "register_project",
        "description": "Register a new project or update an existing project's root path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Project name"},
                "root_path":    {"type": "string", "description": "Absolute path to project root"},
            },
            "required": ["project_name", "root_path"]
        },
    },
    {
        "name": "add_project_keyword",
        "description": (
            "Add a keyword variant for a project. Keywords are used to match Pieces session "
            "summaries and events to projects (e.g., alternate names, abbreviations)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Project name"},
                "keyword":      {"type": "string", "description": "Keyword variant (case-insensitive)"},
            },
            "required": ["project_name", "keyword"]
        },
    },
    {
        "name": "list_projects",
        "description": "List all registered projects and whether their root directories exist on disk.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "save_session_summary",
        "description": (
            "Persist a structured session summary to context.db. Call this: "
            "(1) before ending a session, (2) after completing a major milestone, "
            "(3) whenever context may be lost (compaction, crash, checkpoint). "
            "This is the PRIMARY persistence mechanism when Pieces LTM is unavailable. "
            "Saved summaries are returned by session_briefing at the start of the next session."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Project name"},
                "summary": {
                    "type": "string",
                    "description": (
                        "Structured summary: what was done, key decisions made, "
                        "what's left in-progress, any blockers or gotchas for next session"
                    ),
                },
                "files_changed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of files created or modified this session",
                },
                "entities_registered": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of entities registered this session",
                },
                "checklist_progress": {
                    "type": "object",
                    "description": "Snapshot of checklist counts: {done: N, in_progress: N, pending: N, blocked: N, verified: N}",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID from record_session_intent (links summary to intent)",
                },
            },
            "required": ["project_name", "summary"],
        },
    },
]


def dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    """Route a tool call to its implementation."""
    try:
        if name == "session_briefing":
            return tool_session_briefing(arguments["project_name"])
        elif name == "get_checklist":
            return tool_get_checklist(arguments["project_name"])
        elif name == "mark_checklist_item":
            return tool_mark_checklist_item(
                arguments["project_name"],
                arguments["item_text"],
                arguments["status"],
                arguments.get("note", ""),
            )
        elif name == "record_session_intent":
            return tool_record_session_intent(
                arguments["project_name"],
                arguments["intent"],
                arguments.get("files_to_touch"),
                arguments.get("session_id"),
            )
        elif name == "complete_session_intent":
            return tool_complete_session_intent(
                arguments["project_name"],
                arguments["session_id"],
                arguments.get("outcome", ""),
            )
        elif name == "get_recent_sessions":
            return tool_get_recent_sessions(
                arguments["project_name"],
                int(arguments.get("n", 5)),
            )
        elif name == "get_entity_registry":
            return tool_get_entity_registry(
                arguments["project_name"],
                arguments.get("entity_type"),
            )
        elif name == "register_entity":
            return tool_register_entity(
                arguments["project_name"],
                arguments["name"],
                arguments["entity_type"],
                arguments["file"],
                arguments.get("line"),
            )
        elif name == "search_history":
            return tool_search_history(
                arguments["project_name"],
                arguments["query"],
            )
        elif name == "register_project":
            return tool_register_project(
                arguments["project_name"],
                arguments["root_path"],
            )
        elif name == "add_project_keyword":
            return tool_add_project_keyword(
                arguments["project_name"],
                arguments["keyword"],
            )
        elif name == "list_projects":
            return tool_list_projects()
        elif name == "save_session_summary":
            return tool_save_session_summary(
                arguments["project_name"],
                arguments["summary"],
                arguments.get("files_changed"),
                arguments.get("entities_registered"),
                arguments.get("checklist_progress"),
                arguments.get("session_id"),
            )
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except KeyError as e:
        return json.dumps({"error": f"Missing required argument: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Tool error: {type(e).__name__}: {e}"})


# ── MCP stdio loop ─────────────────────────────────────────────────────────────

def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def send_error(req_id: Any, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def main() -> None:
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError as e:
            send_error(None, -32700, f"Parse error: {e}")
            continue

        method  = msg.get("method", "")
        req_id  = msg.get("id")
        params  = msg.get("params", {})

        # Notifications have no id — no response needed
        if req_id is None and method.startswith("notifications/"):
            continue

        if method == "initialize":
            send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "context-mcp",
                        "version": "1.0.0",
                        "description": "Cross-session AI context server — prevents coding-in-circles",
                    },
                },
            })

        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result_text = dispatch_tool(tool_name, arguments)
            send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}]
                },
            })

        elif req_id is not None:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
