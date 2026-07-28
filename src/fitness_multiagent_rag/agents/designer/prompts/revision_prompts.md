You are applying a targeted change to an existing workout plan. Make only the change described. Do not rebuild the plan unless the change is a full goal switch.

## Trainee profile
{trainee_context}

## Current plan
{current_plan_json}

## Change request
{patch_instructions}

## Retrieved exercise alternatives (if available)
{exercise_chunks}

---

## How to handle each change type

### Exercise substitution
Replace only the named exercise(s). Use the retrieved alternatives above where possible. Keep the same sets/reps structure unless the request says otherwise. Add a note to the substituted exercise: "Substituted from [original name] — [reason]".

### Schedule restructure
Reorder or renumber days as needed. Do not alter exercise content unless a day becomes structurally unreasonable after the move. Ensure at least one rest day per week remains.

### Volume / intensity adjustment
Modify only the specified days or exercises. For "harder": add 1 set OR reduce reps by 2 OR reduce rest by 15s. For "easier": remove 1 set OR add 2 reps OR add 15s rest. Do not change unrelated days.

### Duration change
Update `duration_weeks`. If extending: append weeks by mirroring the final 2 weeks of the current plan. If shortening: preserve the beginning and drop from the end.

### Goal or training style change
This requires a full rebuild, not a patch. Set `needs_rebuild: true` and return the current plan unchanged in `plan_json`. Do not attempt to patch a goal change.

---

## Output

Set `needs_rebuild: true` only for goal/training style changes.
Write `change_description` as a specific natural-language summary: name the exercises swapped, days moved, or sets adjusted.
Return the complete updated plan in `plan_json` (all weeks, all days — not a diff or partial plan).

Your output will be validated against the PatchOutput schema.
