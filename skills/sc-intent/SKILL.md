---
name: sc-intent
description: Record what this session intends to do before starting to code. Use when beginning a coding task, picking up a CHECKLIST item, or switching to a new area of work. Trigger on /sc:intent, "record intent", "I'm going to work on", or before starting any non-trivial code changes.
---

# Record Session Intent

Declare what this session will do **before** writing any code. This prevents file-level collisions between concurrent sessions and leaves a trail for future sessions.

## Procedure

1. **Identify the work.** What CHECKLIST items, bug fixes, or features will this session tackle?

2. **Identify the files.** Which files will be created or modified?

3. **Call `record_session_intent`:**
   ```
   record_session_intent(
     project_name="<PROJECT_NAME>",
     intent="<concise description of what this session will do>",
     files_to_touch=["src/foo.ts", "src/bar.ts"],
     session_id="<optional — auto-generated if omitted>"
   )
   ```

4. **Check for warnings.** The response will warn if another open session has claimed any of the same files. If there is a conflict:
   - Read the conflicting intent to understand what the other session is doing
   - Choose non-overlapping files, or coordinate with the user
   - Do NOT silently proceed on conflicting files

5. **Save the session_id** from the response. You will need it to call `complete_session_intent` when done.

## When done

At the end of the session, or when switching to different work, call:
```
complete_session_intent(
  project_name="<PROJECT_NAME>",
  session_id="<session_id from step 3>",
  outcome="<what was actually accomplished>"
)
```

The outcome should be specific: "Implemented P2.1-P2.4, registered 3 entities, all typechecks pass" — not "worked on stuff."
