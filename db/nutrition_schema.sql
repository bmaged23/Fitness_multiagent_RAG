-- Nutrition plans are independent of workout plans; approval activates a draft.
CREATE TABLE IF NOT EXISTS nutrition_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trainee_id INTEGER NOT NULL REFERENCES trainees(id) ON DELETE CASCADE,
    plan_json TEXT NOT NULL CHECK (json_valid(plan_json)),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_nutrition_plans_trainee_status ON nutrition_plans(trainee_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_nutrition_one_active ON nutrition_plans(trainee_id) WHERE status='active';
CREATE UNIQUE INDEX IF NOT EXISTS idx_nutrition_one_draft ON nutrition_plans(trainee_id) WHERE status='draft';
CREATE TABLE IF NOT EXISTS nutrition_plan_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutrition_plan_id INTEGER NOT NULL REFERENCES nutrition_plans(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
    previous_plan_json TEXT NOT NULL CHECK (json_valid(previous_plan_json)),
    new_plan_json TEXT NOT NULL CHECK (json_valid(new_plan_json)),
    change_description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(nutrition_plan_id, revision_number)
);
