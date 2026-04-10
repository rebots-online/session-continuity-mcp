---
name: sesh-briefing
description: Call session_briefing via context-mcp at the start of every session. Use when beginning work on any registered project, resuming after an interruption, or when you need to understand what happened in prior sessions. AUTO-ACTIVATE on two conditions — (1) no briefing called yet, or (2) briefing was called but context compaction evicted the results (post-compaction amnesia). Trigger on /sesh:briefing, "brief me", "what happened last session", "session start", any new session on a registered project, context compaction/summarization, or agent self-detection that briefing data is missing from working context.
---

# Session Briefing

Call `session_briefing` from the `context-mcp` MCP server to get full cross-session context in one call.

## When to use

- At the **start of every session** before reading files or making plans
- **After context compaction** — compaction evicts tool results; the codemap,
  checklist, and entity data are gone from working context even though a summary
  says "briefing was called." Re-call to reload.
- When resuming after an interruption
- When asked "what happened last session" or "where did we leave off"
- When starting work on any project registered with context-mcp

## Procedure

### Step 1: Regenerate the Project Index (codemap)

**This step is mandatory on every briefing.** The PROJECT_INDEX can be stale from prior
sessions that added, moved, or deleted files. Regenerate it fresh so the briefing
includes an accurate structural map of the codebase.

Run five parallel searches to analyze the project structure:

1. **Code files**: `src/**/*.{ts,py,js,tsx,jsx,kt,swift}`, `lib/**/*.{ts,py,js}`, `packages/**/*.{ts,tsx}`
2. **Documentation**: `docs/**/*.md`, `*.md` (root level), `DOCS/**/*.md`
3. **Configuration**: `*.toml`, `*.yaml`, `*.yml`, `*.json` (exclude node_modules, package-lock)
4. **Tests**: `tests/**/*`, `**/*.test.{ts,py,js}`, `**/*.spec.{ts,py,js}`
5. **Scripts & tools**: `scripts/**/*`, `bin/**/*`, `tools/**/*`

Then extract metadata:
- **Entry points**: main.py, index.ts, cli.py, App.kt, etc.
- **Core modules**: top-level directories with their purpose (1-line each)
- **API surface**: public functions, classes, endpoints (names only, not full signatures)
- **Dependencies**: from package.json, pyproject.toml, build.gradle.kts, Cargo.toml, etc.

Generate **both files as a matched pair** in the project root:

**`PROJECT_INDEX.md`** (~3KB, human-readable):
```markdown
# Project Index: {project_name}

Generated: {YYYY-MM-DD}

> Matched pair: verify PROJECT_INDEX.json has the same generated date.

## Project Structure
{tree view of main directories, 1-2 levels deep}

## Entry Points
- {path} - {1-line purpose}

## Core Modules
### {module_name}
- Path: {path}
- Purpose: {1-line description}

## Configuration
- {config_file}: {purpose}

## Documentation
- {doc_file}: {topic}

## Test Coverage
- {count} test files across {directories}

## Key Dependencies
- {dependency}: {version} - {why it's used}
```

**`PROJECT_INDEX.json`** (~10KB, machine-readable):
```json
{
  "meta": { "project": "...", "generated": "YYYY-MM-DD" },
  "_parity_notice": "Verify PROJECT_INDEX.md has the same generated date",
  "entry_points": [...],
  "modules": [...],
  "config_files": [...],
  "dependencies": [...]
}
```

**Parity rules** (non-negotiable):
- Both files MUST have the same `generated` date
- Both files MUST be in the project root
- No fact may differ between them
- Each file contains a parity notice referencing its sibling

**Size budget**: PROJECT_INDEX.md MUST stay under 5KB. This is a session primer,
not comprehensive documentation. The point is ~3K tokens instead of ~58K for a
full codebase read.

### Step 2: Call session_briefing

Determine the project name (current working directory basename, or ask the user if
ambiguous — call `list_projects` first if unsure), then:

```
session_briefing(project_name="<PROJECT_NAME>")
```

The briefing returns:
- **Project Index** (the codemap you just generated — included automatically)
- Recent git history (last 10 commits, branch, dirty status)
- CHECKLIST.md parsed into structured items with four-state markers
- Incomplete session intents from prior sessions
- Saved session summaries (narrative context from prior sessions)
- Recent Pieces LTM session history
- Named entity registry

### Step 3: Report to the user

Summarize:
- What the last session(s) worked on
- What items are in-progress or blocked
- Any incomplete session intents that need attention
- Current branch and uncommitted changes

### Step 4: Record your intent (if about to start coding)

```
record_session_intent(project_name="<PROJECT_NAME>", intent="<what you will do>", files_to_touch=["path/one", "path/two"])
```

## Do NOT skip the briefing

A session that starts without calling `session_briefing` risks:
- Reimplementing what a prior session already built
- Creating parallel implementations that diverge
- Touching files another session has claimed
- Losing track of CHECKLIST progress
- **Shallow spelunking** — finding the first match and missing the real implementation

## Self-activation (non-negotiable)

This skill must auto-fire on **two** conditions — not just one:

### Condition 1: No briefing called yet
If `session_briefing` has NOT been called in this session.

### Condition 2: Post-compaction amnesia
If `session_briefing` WAS called, but context compaction/summarization has since
evicted the results. **Compaction does not persist tool results into working context.**
It only preserves a summary that a briefing happened — not the codemap, not the
checklist items, not the entity registry.

**How to detect**: if you cannot recall the specific contents of PROJECT_INDEX,
CHECKLIST status, entity registry, or session summaries from the briefing — the
data was evicted. The presence of a conversation summary mentioning "briefing was
called" is NOT a substitute for the actual data.

### In either case:
1. **Stop** whatever you are about to do
2. **Run this skill** immediately — before reading files, before making plans, before writing code
3. **Then** resume the user's request

Do not ask the user for permission. Do not mention that you're "checking first." Just do
it. A session without **live** briefing data is a session that will code in circles. The
cost of a redundant briefing is zero. The cost of a missed briefing is a full session of
wasted work.
