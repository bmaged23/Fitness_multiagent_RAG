Fill in Week 1 exercises for this approved training structure. The structure has already been confirmed — do not change the split, schedule, or duration.

## Trainee profile
{trainee_context}

## Injuries / limitations
{injuries_text}

## Approved structure
- Split: {split_type} | {days_per_week} days/week | {rep_style}
- Goal: {goal} | Level: {difficulty} | Equipment: {equipment}
- Duration: {duration_weeks} weeks
- Schedule:
{day_schedule}

## User feedback (apply if any)
{user_feedback}

## Retrieved exercise options
{exercise_chunks}

---

## Instructions

For each **non-REST day**, generate 4–6 exercises:
- Equipment: use ONLY {equipment} — no exceptions
- Injuries: never include contraindicated exercises (see injuries above)
- Rep style: follow {rep_style} for working sets
- Day focus: match the day label (push muscles on Push day, pull muscles on Pull day, etc.)
- Volume by level:
  - Beginner/Novice: 3 sets per exercise
  - Intermediate: 3–4 sets per exercise
  - Advanced: 4–5 sets per exercise

For each **REST day**: rest_day=true, exercises=[]

## Output

Return a PlanSchema with:
- goal: {goal}
- difficulty: {difficulty}
- duration_weeks: {duration_weeks}
- equipment_available: [{equipment}]
- weeks: exactly ONE week (week=1), containing all 7 days matching the schedule above

Week 2 onward will be generated programmatically — output Week 1 only.
