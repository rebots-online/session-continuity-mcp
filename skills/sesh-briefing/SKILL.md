---
name: sesh-briefing
description: Call session_briefing via context-mcp at the start of every session. Use when beginning work on any registered project, resuming after an interruption, or when you need to understand what happened in prior sessions. Trigger on /sesh:briefing, "brief me", "what happened last session", "session start", or any new session on a registered project.
---

# Session Briefing

Call `session_briefing` from the `context-mcp` MCP server to get full cross-session context in one call.

## When to use

- At the **start of every session** before reading files or making plans
- When resuming after a context compaction or interruption
- When asked "what happened last session" or "where did we leave off"
- When starting work on any project registered with context-mcp

## Procedure

1. **Determine the project name.** Use the current working directory basename, or ask the user if ambiguous. If unsure, call `list_projects` first to see registered projects.

2. **Call `session_briefing`** with the project name:
   ```
   session_briefing(project_name="<PROJECT_NAME>")
   ```

3. **Review the briefing.** It returns:
   - Recent git history (last 10 commits, branch, dirty status)
   - CHECKLIST.md parsed into structured items with four-state markers
   - Incomplete session intents from prior sessions
   - Recent Pieces LTM session history
   - Named entity registry

4. **Report to the user.** Summarize:
   - What the last session(s) worked on
   - What items are in-progress or blocked
   - Any incomplete session intents that need attention
   - Current branch and uncommitted changes

5. **Record your own intent** if you are about to start coding:
   ```
   record_session_intent(project_name="<PROJECT_NAME>", intent="<what you will do>", files_to_touch=["path/one", "path/two"])
   ```

## Do NOT skip the briefing

A session that starts without calling `session_briefing` risks:
- Reimplementing what a prior session already built
- Creating parallel implementations that diverge
- Touching files another session has claimed
- Losing track of CHECKLIST progress
