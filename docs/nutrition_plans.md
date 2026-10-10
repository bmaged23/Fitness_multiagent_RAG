# Nutrition plan persistence

Coach stores nutrition plans independently from workout programs in the same SQLite database.

- `nutrition_plans` holds validated JSON, trainee ownership, draft/active/archived status, and timestamps. Partial unique indexes enforce at most one active plan and one pending draft per trainee.
- `nutrition_plan_revisions` records ordered before/after snapshots and descriptions, including the initial draft. Revisions of an active plan become a separate draft; the active plan remains unchanged until approval.
- Saving creates or updates a draft. Approval atomically archives the old active nutrition plan and activates the specified draft. A request to view details does not activate it.

The plan schema contains a goal, daily calories and protein/carbohydrate/fat targets, meals and portions with alternatives, preferences/allergies/restrictions, start/review dates, and notes. Validation checks required fields, finite nonnegative macros, positive calories, date ordering, and approximate macro/calorie consistency. This validates storage structure; it does not independently verify medical suitability, food allergen content, or actual meal nutrient totals.

Coach tools: `save_nutrition_plan`, `get_nutrition_plan`, `approve_nutrition_plan`, `revise_nutrition_plan`, and `get_nutrition_plan_history`. Tool calls scope records to the provided trainee ID, following the existing app's trusted-agent identity model. User-facing messages use plain meal-plan language rather than JSON or database IDs.

The additive schema lives in `db/nutrition_schema.sql`. `scripts/init_db.py` installs it for new or existing databases; nutrition storage also initializes the tables idempotently on first use. It does not alter workout tables or create an approved nutrition plan automatically.

Examples: “Create a nutrition plan for me,” “Show me my meal plan,” or “Change breakfast in my nutrition plan.” Coach loads existing data first, gathers missing dietary information, saves a draft, and asks for approval before activation.

Offline verification:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_nutrition_plans.py -q
```
