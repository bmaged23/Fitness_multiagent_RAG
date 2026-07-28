---
name: retrieval-coverage-loop
description: Full multi-phase retrieval loop — decompose, search, validate relevance per need, rewrite on failure, coverage check, gap fill, return grouped JSON.
---

# retrieval-coverage-loop

## When to invoke

Any time the Coach or Program Designer needs grounded fitness content from the vector database. Always use this skill — never search without decomposing first.

## Phase 1 — Decompose the request

Call `decompose_query` with the full request and any trainee context available.

The decomposer will return 1–4 needs. Each need has:
- `description`: what this need covers
- `query_text`: optimized semantic search string
- `collection`: which collection to search
- `goal / level / equipment`: slot filters (null if not applicable)
- `top_k`: how many results to fetch

## Phase 2 — Search and validate each need

Process needs one by one:

```
for each need:
  1. call search_programs(query, goal, level, equipment, top_k)
       OR search_exercises(query, goal, level, equipment, top_k)
     depending on need.collection

  2. call validate_chunk_relevance(need_description, chunks_json)
     → returns true/false

  3. if false AND search_count < 6:
       call rewrite_search_query(need_description, original_query, poor_chunks_json)
       → returns list of rewritten sub-queries
       call search again with the first rewritten query
       add results to pool (accept regardless — one retry max per need)

  4. if true:
       add chunks to pool
       mark need as satisfied
```

**Relevance criteria for validate_chunk_relevance:**
- TRUE: goal/level/equipment aligns with the need AND text is topically correct
- FALSE: completely wrong domain, wrong equipment, or entirely off-topic
- NEVER false just because the chunk is a summary without a full schedule

## Phase 3 — Coverage check (run after all needs are processed)

Call `check_retrieval_coverage(original_query, needs_json, pool_json)`.

Returns:
- `satisfied`: list of need descriptions the pool covers
- `gaps`: list of need descriptions still missing
- `confident`: bool

For each gap (if `search_count < 6`):
1. Formulate a new targeted sub-query for that gap
2. Search the appropriate collection
3. Validate and add to pool

Skip Phase 3 entirely if `confident` is already clearly true from Phase 2 results.

## Search ceiling

Track total calls to `search_programs` + `search_exercises`. Stop at **6**. Never exceed this.

## Final output

After all phases complete, return a single JSON array — one entry per subquery executed:

```json
[
  {
    "subquery": "exact query string sent to the search tool",
    "collection": "fitness_programs",
    "chunks": [
      { "title": "Program Name", "score": 0.82, "text": "full chunk text..." }
    ]
  },
  {
    "subquery": "exact query string sent to the search tool",
    "collection": "fitness_exercises",
    "chunks": [
      { "title": "Exercise Name", "score": 0.76, "text": "full chunk text..." }
    ]
  }
]
```

If overall confidence is low (all scores < 0.55 OR majority of needs are gaps), append:
```json
{ "confident": false }
```
as the last element.

## Hard prohibitions

- Do NOT call `write_file` — output goes in the final message only
- Do NOT skip `validate_chunk_relevance` after each search
- Do NOT skip `check_retrieval_coverage` unless confidence is clearly established
- Do NOT recommend, suggest, or interpret — retrieve and return JSON only
- Do NOT add any prose outside the JSON array
