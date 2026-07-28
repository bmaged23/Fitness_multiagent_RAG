You are synthesizing a new workout plan from retrieved program references and exercise options. Combine them into one coherent plan for this specific trainee.

## Trainee profile
{trainee_context}

## Original request
{request_text}

## Retrieved program references
{program_chunks}

## Retrieved exercise options
{exercise_chunks}

---

## Step 1 — Choose a structure from the program references

Read the program summaries and pick the best structural template for this trainee's goal and fitness level:
- **Training split**: full body / upper-lower / push-pull-legs / body part
- **Weekly frequency**: days/week appropriate for their level
- **Rep style**: strength (3–6), hypertrophy (8–12), endurance (15+)
- **Deload**: include a lighter week every 4 weeks for Intermediate/Advanced programs ≥ 8 weeks

## Step 2 — Fill the structure with exercises

Select from the retrieved exercise options above. Each exercise must:
- Use only the trainee's available equipment — no exceptions
- Be appropriate for the training day's focus (push muscles on push day, etc.)
- NOT be contraindicated by the trainee's injuries/limitations
- Match the trainee's fitness level in sets/reps/intensity:
  - Beginner/Novice: 2–3 sets, 10–12 reps, 3 training days/week
  - Intermediate: 3–4 sets, 8–12 reps, 4 days/week
  - Advanced: 4–5 sets, 4–8 reps, 5–6 days/week

## Step 3 — Plan-level fields

- `goal`: use the exact value from the dataset goal list that best matches the request
- `difficulty`: match the trainee's fitness_level (Beginner / Novice / Intermediate / Advanced)
- `duration_weeks`: from the request, or default — Beginner 8, Intermediate 12, Advanced 16
- `equipment_available`: list the trainee's equipment categories

## Step 4 — Output Week 1 and Week 2 ONLY

**Generate exactly 2 weeks** in the `weeks` list:
- Week 1: baseline (easier — fewer sets/reps)
- Week 2: slightly harder than Week 1 (show the progression direction)

Every week must include at least one rest day (`rest_day: true`, `exercises: []`).
Weeks 3 through `duration_weeks` will be expanded programmatically with linear overload.

Your output will be validated against the PlanSchema. Populate every required field.
