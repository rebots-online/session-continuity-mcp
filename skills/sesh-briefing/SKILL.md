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

### Do NOT regenerate the Project Index here

`PROJECT_INDEX.md` + `PROJECT_INDEX.json` are maintained **out of band** by a
dedicated background indexing agent (cron). Working agents — architect and coder
alike — consume the index; they never produce it. Regenerating the index inside
a briefing burns context budget on work the background agent already owns, and
defeats the whole point of having a token-efficient codemap.

If the index is missing or stale, that is a background-agent problem. The
briefing will surface a warning (see Step 2 output); do **not** derail the
session to rebuild it. Note the warning, continue with the user's task, and
trust that the indexer will catch up on its next tick.

### Step 1: Call session_briefing

Determine the project name (current working directory basename, or ask the user if
ambiguous — call `list_projects` first if unsure), then:

```
session_briefing(project_name="<PROJECT_NAME>")
```

The briefing returns:
- **Project Index** (codemap produced by the background indexer — included automatically; may carry a staleness warning if the indexer is behind)
- Recent git history (last 10 commits, branch, dirty status)
- CHECKLIST.md parsed into structured items with four-state markers
- Incomplete session intents from prior sessions
- Saved session summaries (narrative context from prior sessions)
- Recent Pieces LTM session history
- Named entity registry

### Step 2: Report to the user

Summarize:
- What the last session(s) worked on
- What items are in-progress or blocked
- Any incomplete session intents that need attention
- Current branch and uncommitted changes

### Step 3: Record your intent (if about to start coding)

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

This skill fires on **two** conditions, with a critical **exception** for the coder phase:

### Condition 1: No briefing called yet
If `session_briefing` has NOT been called in this session.
**Action**: Run this skill immediately.

### Condition 2: Post-compaction during architect phases (1–3)
If `session_briefing` WAS called, but context compaction/summarization has since
evicted the results. **Compaction does not persist tool results into working context.**
It only preserves a summary that a briefing happened — not the codemap, not the
checklist items, not the entity registry.

**How to detect**: if you cannot recall the specific contents of PROJECT_INDEX,
CHECKLIST status, entity registry, or session summaries from the briefing — the
data was evicted. The presence of a conversation summary mentioning "briefing was
called" is NOT a substitute for the actual data.

**Action**: Run this skill immediately to reload full context.

### Exception: Post-compaction during coder phase (4)
If compaction occurs while you are executing CHECKLIST.md tasks, **do NOT re-brief**.
Your instinct after compaction will be to "get your bearings" by reading around the
codebase. **That instinct is wrong.** CHECKLIST.md is the compaction firewall — every
task is self-contained with exact file paths, entity names, signatures, parameters,
and acceptance criteria.

**Action**: Re-read CHECKLIST.md. Find the task you were on. Put on tunnel vision.
Continue executing. Do NOT spelunk. Do NOT read architecture docs. Do NOT call
`session_briefing`. If a CHECKLIST.md task doesn't have enough information to execute,
that's an architect bug — stop coding and return to architect phase (where you WILL
need the briefing).

### For conditions 1–2:
1. **Stop** whatever you are about to do
2. **Run this skill** immediately — before reading files, before making plans, before writing code
3. **Then** resume the user's request

Do not ask the user for permission. Do not mention that you're "checking first." Just do
it. A session without **live** briefing data is a session that will code in circles. The
cost of a redundant briefing is zero. The cost of a missed briefing is a full session of
wasted work.
