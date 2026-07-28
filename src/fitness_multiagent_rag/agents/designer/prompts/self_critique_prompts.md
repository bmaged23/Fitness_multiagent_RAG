You are reviewing a 2-week workout plan template for coherence, goal fit, and injury compliance. The plan was assembled from multiple source programs. Identify specific problems and output only the exercise-level changes needed — do NOT reproduce the full plan.

## Trainee profile
{trainee_context}

## Injuries / limitations
{injuries_text}

## Source programs used in synthesis
{source_chunks_summary}

## Plan to review (2-week template)
{plan_json}

---

## Check 1 — Coherence

Does the plan make sense as a whole?
- Does the split label match the actual exercises? (e.g., a "Push" day should not contain rows)
- Is weekly volume consistent? Flag days with dramatically more or fewer exercises than others
- Do rep ranges match the difficulty label? (Beginner plans should not have 4×3 heavy singles)
- Obvious redundancies — same exercise or same muscle group hit identically twice in the same week?

## Check 2 — Goal fit

Does the training style match the trainee's stated goal?
- **Bodybuilding / Muscle & Sculpting**: moderate weight, 8–12 reps, mix of compounds and isolation
- **Powerbuilding / Powerlifting**: compound-heavy, 3–6 reps for primary lifts, minimal isolation
- **Athletics**: functional movements, conditioning elements
- **Bodyweight Fitness / At-Home**: no gym equipment should appear

## Check 3 — Injury constraint compliance

Check every exercise against the injuries/limitations. Flag any contraindicated exercise:
- **Knee pain**: barbell squats, deep lunges, leg press → goblet squats, leg curls, step-ups, hip thrusts
- **Lower back**: deadlifts, good mornings → rack pulls, cable pull-throughs, kettlebell swings
- **Shoulder impingement**: overhead press, upright rows → neutral-grip rows, face pulls, incline dumbbell press
- **Wrist issues**: barbell curls, front rack exercises → cable or dumbbell alternatives

---

## Output format

Output ONLY the changes needed — do NOT reproduce the plan.

- Set `changed: true` if any change is required, `false` if the plan is sound as-is.
- Write `critique_notes` in 1–2 sentences explaining what changed and why (or why nothing changed).
- For each problem exercise, add one entry to `changes`:
  - `week`: week number (1 or 2)
  - `day`: day number
  - `original_name`: the exact exercise name to find
  - `action`: "remove" or "replace"
  - `replacement`: full Exercise object (name, sets, reps, rest_seconds, equipment, muscle_group, notes) — required when action is "replace", null when "remove"
  - `reason`: one sentence

If no changes are needed, return `changed: false`, a brief `critique_notes`, and an empty `changes` list.
