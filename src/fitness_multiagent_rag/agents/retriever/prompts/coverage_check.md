You are checking whether the retrieved chunk pool covers all identified retrieval needs.

## IMPORTANT: Data format
The fitness_programs collection stores PROGRAM SUMMARIES — title, goal, level, equipment, duration, and description. They do NOT contain full day-by-day exercise schedules. This is expected. A need is SATISFIED if the pool contains topically aligned chunks — not if it contains a complete workout plan.

## Original request
{original_query}

## Needs identified
{needs}

## Retrieved chunk pool
{chunks_text}

## How to evaluate each need

A need is **satisfied** if the pool contains chunks where:
- The goal, level, or equipment metadata aligns with the need
- The text or description is topically about the right training domain

A need is a **gap** only if the pool contains NO chunks relevant to it — wrong goal, wrong equipment, or completely off-topic.

## Confidence

Set `confident: true` if the satisfied needs cover the core of the original request well enough for the Designer to synthesize a plan.
Set `confident: false` only if the majority of needs are gaps, or all retrieved scores were very low (< 0.55).

## Output — JSON only, no explanation

```json
{
  "satisfied": ["description of need 1", "description of need 3"],
  "gaps": ["description of need 2"],
  "confident": true
}
```
