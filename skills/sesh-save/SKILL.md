---
name: sesh-save
description: Save current session context to context.db. Use proactively after completing a milestone, before context compaction, when switching tasks, or when the user says "save", "checkpoint", "persist". Also trigger automatically whenever any other checkpoint/save mechanism fires. Trigger on /sesh:save, "save session", "checkpoint", "persist context", or any context-loss risk event.
---

# Save Session Context

Persist the current session's state to `context.db` so the next session can pick up where this one left off. This is **critical** when Pieces LTM is unavailable — without it, session context dies with the session.

## When to call (mandatory)

- **Before session ends** — always, no exceptions
- **After completing a major milestone** — e.g., finishing a CHECKLIST section
- **Before context compaction** — if you detect the context window is filling up
- **When switching between tasks** — save the old context before starting new work
- **When any external checkpoint fires** — if another tool saves/checkpoints state, call this too (a checkpoint without session context = Circular Programming Express)
- **On user request** — "save", "checkpoint", "persist"

## Procedure

1. **Gather what happened.** Collect:
   - A structured summary of what was accomplished, decisions made, and what's in-progress
   - Files created or modified
   - Entities registered (by name)
   - Current CHECKLIST progress counts

2. **Call `save_session_summary`:**
   ```
   save_session_summary(
     project_name="<PROJECT_NAME>",
     summary="<structured summary: what was done, decisions, in-progress items, blockers, gotchas for next session>",
     files_changed=["path/to/file1", "path/to/file2"],
     entities_registered=["EntityName1", "EntityName2"],
     checklist_progress={"done": 5, "in_progress": 2, "pending": 10, "blocked": 0, "verified": 3},
     session_id="<session_id from record_session_intent, if available>"
   )
   ```

3. **Confirm to the user.** Report:
   - Summary was saved
   - The session_id it was linked to
   - How many files/entities were recorded

## Summary structure (first line = title)

Write the summary so the **first line** serves as a title/headline. Subsequent lines should cover:
- What was accomplished (specific: files, functions, checklist items)
- Key decisions made and why
- What's in-progress or partially implemented
- Blockers or gotchas the next session needs to know
- Any architecture decisions that aren't yet in CHECKLIST.md

## Auto-save triggers

You should call this **proactively** without being asked:
- When you notice conversation context is getting long
- After every 3-5 significant code changes
- Before any operation that might fail or take a long time
- When the user hasn't explicitly asked but you've been working for a while

The cost of saving too often is zero. The cost of not saving is starting from scratch.
