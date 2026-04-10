---
name: sesh-done
description: Complete the current session intent and update checklist items. Use at the end of a coding session, when wrapping up work, or when the user says "we're done", "wrap up", "end session". Trigger on /sesh:done, "session done", "wrap up", "end session", "mark complete".
---

# Complete Session

Wrap up the current session by completing the session intent, marking checklist items, and registering any new entities.

## Procedure

1. **Review what was accomplished.** Look at:
   - Files created or modified in this session
   - CHECKLIST items that were worked on
   - Entities (functions, classes, endpoints) that were created or moved

2. **Mark checklist items.** For each item worked on:
   ```
   mark_checklist_item(
     project_name="<PROJECT_NAME>",
     item_text="<text of the checklist item>",
     status="done",        # or "in_progress" if not finished
     note="<what was done>"
   )
   ```
   Also update CHECKLIST.md directly with the appropriate marker:
   - `[X]` if code was written but not yet verified by running it
   - `✅` if the verification command was run and output matched acceptance criteria
   - `[/]` if work started but the item is not complete

3. **Register new entities.** For each function, class, type, endpoint, or other named entity created or moved:
   ```
   register_entity(
     project_name="<PROJECT_NAME>",
     name="<entity name>",
     entity_type="function",  # or class, interface, type, constant, endpoint, table
     file="<file path>",
     line=<line number>
   )
   ```

4. **Save the session summary** (CRITICAL — do this BEFORE completing intent):
   ```
   save_session_summary(
     project_name="<PROJECT_NAME>",
     summary="<first line = title>\n<what was done, decisions made, in-progress items, blockers, gotchas for next session>",
     files_changed=["path/to/modified/files"],
     entities_registered=["EntityName1", "EntityName2"],
     checklist_progress={"done": N, "in_progress": N, "pending": N, "blocked": N, "verified": N},
     session_id="<session_id from record_session_intent>"
   )
   ```
   This persists the session narrative to context.db. Without this, the next session starts blind.

5. **Regenerate the Project Index (codemap).** The session changed files — the
   PROJECT_INDEX must reflect the final state. Follow the same index generation
   procedure as `/sesh:briefing` Step 1:
   - Run parallel searches (code, docs, config, tests, scripts)
   - Extract metadata (entry points, modules, API surface, dependencies)
   - Write both `PROJECT_INDEX.md` and `PROJECT_INDEX.json` as a matched pair
   - Verify parity (same generated date, same facts, both in project root)
   - Keep PROJECT_INDEX.md under 5KB (token-efficient session primer)

6. **Complete the session intent:**
   ```
   complete_session_intent(
     project_name="<PROJECT_NAME>",
     session_id="<session_id from record_session_intent>",
     outcome="<specific summary of what was accomplished>"
   )
   ```

7. **Report to the user.** Summarize:
   - Checklist items completed (with state)
   - Entities registered
   - Session summary saved (confirm it persisted)
   - Project index refreshed
   - Any items left in-progress for the next session
   - The session_id and outcome recorded

## If no intent was recorded

If `record_session_intent` was never called this session, note this in the outcome and call it retroactively before completing:
```
record_session_intent(project_name="<PROJECT_NAME>", intent="<retroactive description>")
# then:
save_session_summary(project_name="<PROJECT_NAME>", summary="<full summary>", session_id="<returned id>")
# then:
complete_session_intent(project_name="<PROJECT_NAME>", session_id="<returned id>", outcome="<what happened>")
```

## Order matters

Always: `save_session_summary` THEN `complete_session_intent`. If the session crashes between the two calls, the summary is already persisted. The intent completion is nice-to-have; the summary is critical.
