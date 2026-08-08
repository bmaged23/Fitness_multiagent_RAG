Classify the trainee's message into exactly one intent.

## Trainee message
"{user_message}"

## Context
- Trainee has an active workout plan: {has_active_plan}
- Recent memory snippet: {memory_snippet}

## Intent options

| Intent | When to use |
|---|---|
| `new_plan` | Trainee explicitly wants a brand-new workout program created |
| `revision` | Trainee wants to change, swap, or adjust their existing plan |
| `exercise_lookup` | Question about specific exercises, muscles, or equipment — NOT a full plan |
| `log_progress` | Trainee reporting a completed workout, body weight, or progress update |
| `plan_question` | Question about their current plan: today's session, what week, what exercises |
| `general_chat` | Fitness/nutrition/health questions, motivation, general conversation |
| `intake` | New trainee with no profile, or trainee wants to update their profile details |

Rules:
- If the trainee has no active plan and asks to "start" or "begin training", use `intake` or `new_plan`
- Prefer `plan_question` over `general_chat` when the trainee clearly references their own plan
- Prefer `log_progress` when the trainee says they "did", "completed", or "finished" a workout

Return the single best intent and a confidence score (0.0–1.0).
