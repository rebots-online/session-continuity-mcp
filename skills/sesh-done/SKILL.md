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

4. **Complete the session intent:**
   ```
   complete_session_intent(
     project_name="<PROJECT_NAME>",
     session_id="<session_id from record_session_intent>",
     outcome="<specific summary of what was accomplished>"
   )
   ```

5. **Report to the user.** Summarize:
   - Checklist items completed (with state)
   - Entities registered
   - Any items left in-progress for the next session
   - The session_id and outcome recorded

## If no intent was recorded

If `record_session_intent` was never called this session, note this in the outcome and call it retroactively before completing:
```
record_session_intent(project_name="<PROJECT_NAME>", intent="<retroactive description>")
# then immediately:
complete_session_intent(project_name="<PROJECT_NAME>", session_id="<returned id>", outcome="<what happened>")
```
