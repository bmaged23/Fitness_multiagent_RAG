Propose a compact training structure for this trainee. Output the skeleton only — no exercises.

## Trainee profile
{trainee_context}

## Request
{request_text}

## Retrieved program references
{program_chunks}

---

Choose the best fit from the references and the trainee's profile:

**split_type** — pick one: "Full Body", "Upper/Lower", "Push/Pull/Legs", "Body Part"
- Full Body: best for Beginner/Novice, ≤3 days/week
- Upper/Lower: best for Novice/Intermediate, 4 days/week
- Push/Pull/Legs: best for Intermediate/Advanced, 6 days/week
- Body Part: best for Advanced, 5-6 days/week

**days_per_week** — how many training days (rest of the 7 are REST)

**rep_style** — pick one:
- "Strength (3–6 reps)" — for Powerlifting, Powerbuilding goals
- "Hypertrophy (8–12 reps)" — for Bodybuilding, Muscle & Sculpting goals
- "Endurance (15+ reps)" — for Athletics, general fitness goals

**duration_weeks** — from the request, or default: Beginner 8 / Intermediate 12 / Advanced 16

**day_schedule** — exactly 7 strings (Mon–Sun), e.g.:
  ["Full Body A", "REST", "Full Body B", "REST", "Full Body C", "REST", "REST"]

**goal / difficulty / equipment_available** — copy from the trainee profile using exact allowed values.

**rationale** — 1 sentence explaining why this structure fits this specific trainee.
