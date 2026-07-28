---
name: plan-revision
description: Full decision tree for revision requests — classify change scope, decide whether to call the Retriever, patch or rebuild accordingly.
---

# plan-revision

## When to invoke

When the Designer receives a revision request (not a new plan from scratch).

## Step 1 — Load context

Call `load_context(trainee_id)` to get both trainee profile and current active plan.
If no active plan exists → treat as a new plan request.

## Step 2 — Classify the change scope

### Structural-only change — NO Retriever call needed
Examples: "move leg day to Thursday", "add a rest day on Friday", "extend to 12 weeks"
- Call `patch_existing_plan(current_plan_json, patch_instructions, "[]", trainee_id)` directly.
- Do NOT call the Retriever.
- Call `validate_and_critique(..., run_critique=false)`.

### Exercise substitution — CHECK session context first
Examples: "swap squats for something knee-friendly", "replace bench press with dumbbell alternative"
- If suitable alternatives are already in the context from this session: call `patch_existing_plan` with those chunks.
- If not: call `task(subagent_type="retriever", description="knee-friendly lower body exercises dumbbell only")`.
  Then call `patch_existing_plan` with the retrieved chunks.
- Call `validate_and_critique(..., run_critique=false)` unless retrieval returned 3+ program chunks.

### Volume or intensity change
Examples: "too many sets", "make week 1 easier", "add an exercise to chest day"
- Call `patch_existing_plan` with the patch instructions and `"[]"` for chunks.
- Do NOT call the Retriever.
- Call `validate_and_critique(..., run_critique=false)`.

### Goal or training style change — FULL REBUILD
Examples: "switch from bodybuilding to powerlifting", "I want a calisthenics program"
- Call `task(subagent_type="retriever", description=...)` with the new goal.
- Call `synthesize_new_plan`.
- Call `validate_and_critique(..., run_critique=true)`.
- Call `save_plan` with `is_revision=false` (creates new plan, archives old).

## Step 3 — Save

Always call `save_plan` with `is_revision=true` (except full goal rebuilds → `is_revision=false`).

## Step 4 — triggered_by priority

`self_critique` > `validation_fix` > `user_request`
Use the highest-priority trigger that fired.
