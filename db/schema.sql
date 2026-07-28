PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- trainees
-- Identity: name + secondary_id together are unique.
-- Name alone is never sufficient for identity resolution.
-- injuries_limitations lives here — never duplicated into plan_json.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trainees (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT    NOT NULL,
    secondary_id         TEXT    NOT NULL,          -- phone, email, or external trainee_id
    age                  INTEGER,
    gender               TEXT,
    fitness_level        TEXT,                      -- beginner / intermediate / advanced
    equipment_available  TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    injuries_limitations TEXT,
    goal                 TEXT,
    created_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (name, secondary_id)
);

-- ---------------------------------------------------------------------------
-- plans
-- One active plan per trainee at a time (enforced by Coach logic, not DB).
-- plan_json stores the full validated plan_schema.py structure.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plans (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trainee_id     INTEGER NOT NULL REFERENCES trainees(id) ON DELETE CASCADE,
    difficulty     TEXT,
    duration_weeks INTEGER,
    plan_json      TEXT    NOT NULL DEFAULT '{}',
    status         TEXT    NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'completed', 'archived')),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_plans_trainee_status ON plans (trainee_id, status);

-- ---------------------------------------------------------------------------
-- plan_revisions
-- Full audit trail: previous and new plan_json kept for every revision.
-- triggered_by tracks whether the revision came from the user, Designer
-- self-critique, or a structural validation fix.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plan_revisions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id             INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    revision_number     INTEGER NOT NULL,
    change_description  TEXT,
    previous_plan_json  TEXT    NOT NULL DEFAULT '{}',
    new_plan_json       TEXT    NOT NULL DEFAULT '{}',
    triggered_by        TEXT    NOT NULL
                        CHECK (triggered_by IN ('user_request', 'self_critique', 'validation_fix')),
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (plan_id, revision_number)
);

-- ---------------------------------------------------------------------------
-- progress_logs
-- One row per check-in. completed_workouts is a JSON array of workout ids/names.
-- plan_id is nullable — logs persist even if the plan is later archived.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS progress_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trainee_id          INTEGER NOT NULL REFERENCES trainees(id) ON DELETE CASCADE,
    plan_id             INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    log_date            TEXT    NOT NULL,           -- ISO date: YYYY-MM-DD
    weight_kg           REAL,
    completed_workouts  TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_progress_logs_trainee_date ON progress_logs (trainee_id, log_date);

-- ---------------------------------------------------------------------------
-- coach_memory
-- Exactly one row per trainee (UNIQUE constraint).
-- summary_text is the rolling salience-truncated summary.
-- session_count_since_truncation triggers the next salience pass when it
-- reaches MEMORY_TRUNCATION_SESSION_COUNT (defined in config/settings.py).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coach_memory (
    id                             INTEGER PRIMARY KEY AUTOINCREMENT,
    trainee_id                     INTEGER NOT NULL UNIQUE REFERENCES trainees(id) ON DELETE CASCADE,
    summary_text                   TEXT    NOT NULL DEFAULT '',
    session_count_since_truncation INTEGER NOT NULL DEFAULT 0,
    last_updated                   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
