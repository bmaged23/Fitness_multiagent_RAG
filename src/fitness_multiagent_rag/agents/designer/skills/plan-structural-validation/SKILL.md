---
name: plan-structural-validation
description: Run all three structural rule checks on a draft plan — equipment match, rest days, difficulty alignment. Always runs before save_plan.
---

# plan-structural-validation

## When to invoke

After every `synthesize_new_plan` or `patch_existing_plan` call, before `save_plan`. Never skip.

## Step 1 — Call validate_and_critique

Call `validate_and_critique(plan_json, trainee_id, source_chunks_json, run_critique)`.

- Set `run_critique=true` only when synthesizing a new plan from multiple source programs.
- Set `run_critique=false` for simple revisions that did not pull in new retrieval.
- Pass the chunks JSON from the Retriever as `source_chunks_json` (or `"[]"` if not applicable).

Returns:
- `passed`: true if no fatal failures
- `failures`: list of failure messages (may include auto-fix notifications for rest days)
- `plan_json`: the final plan after auto-fixes and optional critique — always use this version
- `critique_notes`: what the self-critique changed (only when run_critique=true)

## Step 2 — Interpret and act

**`passed: true`** → use the returned `plan_json` and proceed to `save_plan`.

**`passed: false` — equipment failures** →
1. Identify which exercises have equipment mismatches from the `failures` list.
2. Call `task(subagent_type="retriever", description="...")` with a targeted query for that muscle group + trainee equipment.
3. Call `patch_existing_plan` with the retrieved alternatives to substitute the flagged exercises.
4. Re-call `validate_and_critique` on the patched plan.

**`passed: false` — difficulty gap > 1 level** →
1. This is a synthesis error. Call `synthesize_new_plan` again with explicit instruction to match the trainee's level.
2. Re-call `validate_and_critique`.

**Maximum 2 re-validate cycles.** If still failing after 2 cycles, proceed with the best available plan and include remaining failures in `change_description`.

## Step 3 — Set triggered_by for save_plan

- Auto-fix applied (rest day): `triggered_by = 'validation_fix'`
- Self-critique changed the plan: `triggered_by = 'self_critique'`
- Validation passed cleanly: `triggered_by = 'user_request'`
- If both auto-fix and critique fired: use `'self_critique'` (most significant)
