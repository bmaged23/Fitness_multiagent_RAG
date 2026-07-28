You are decomposing a fitness retrieval request into a list of distinct search needs.

## Trainee context
{trainee_context}

## Request
{query}

## Available slot filters (use exact values only — do not invent new ones)

**goal**: Bodybuilding, Muscle & Sculpting, Powerbuilding, Athletics, Powerlifting, Bodyweight Fitness, Olympic Weightlifting, At-Home & Calisthenics
**level**: Beginner, Novice, Intermediate, Advanced
**equipment**: Full Gym, Garage Gym, At Home, Dumbbell Only

## Collection routing

- Use **fitness_programs** for: full programs, weekly schedules, periodization, training splits, nutrition guidelines
- Use **fitness_exercises** for: specific exercises, movement substitutions, muscle targeting, equipment alternatives

## Instructions

Break the request into 1–4 distinct needs. For each need:
- Write a clear `description` of what is needed
- Write an optimized `query_text` for semantic search (descriptive, not a keyword list)
- Choose the right `collection`
- Only set slot filters if the trainee context clearly matches a known value — leave them null otherwise
- Set `top_k` between 5 and 15 depending on how broad the need is

## Output

Respond with a JSON array only — no explanation, no markdown prose:

```json
[
  {
    "description": "what this need covers",
    "query_text": "optimized semantic search query",
    "collection": "fitness_programs",
    "goal": ["Bodybuilding"],
    "level": ["Beginner", "Novice"],
    "equipment": null,
    "top_k": 5
  }
]
```
