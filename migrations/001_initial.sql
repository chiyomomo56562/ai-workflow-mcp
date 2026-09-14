CREATE TABLE IF NOT EXISTS workflow (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    session_id TEXT,
    project_path TEXT,
    current_state TEXT NOT NULL CHECK (current_state IN ('DISCOVERY', 'WAITING_CONTEXT_INPUT', 'PLANNING', 'WAITING_APPROVAL', 'IMPLEMENTING', 'REVIEWING', 'COMPLETED')),
    current_plan_version INTEGER,
    approved_plan_version INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (approved_plan_version IS NULL OR current_plan_version IS NOT NULL),
    CHECK (approved_plan_version IS NULL OR approved_plan_version <= current_plan_version)
);
CREATE INDEX IF NOT EXISTS idx_workflow_session_id ON workflow(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_project_path ON workflow(project_path);
CREATE INDEX IF NOT EXISTS idx_workflow_state ON workflow(current_state);

CREATE TABLE IF NOT EXISTS artifact (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('CONTEXT', 'PLAN', 'APPROVAL', 'IMPLEMENTATION', 'REVIEW', 'USER_CONTEXT_REQUEST', 'USER_CONTEXT_RESPONSE', 'CONTEXT_REQUIREMENT')),
    plan_version INTEGER,
    artifact_version INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflow(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_artifact_workflow ON artifact(workflow_id);
CREATE INDEX IF NOT EXISTS idx_artifact_workflow_type ON artifact(workflow_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifact_plan_version ON artifact(workflow_id, plan_version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_artifact_plan_version ON artifact(workflow_id, plan_version) WHERE artifact_type = 'PLAN';
CREATE UNIQUE INDEX IF NOT EXISTS uq_artifact_approval_version ON artifact(workflow_id, plan_version) WHERE artifact_type = 'APPROVAL';

CREATE TABLE IF NOT EXISTS workflow_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('WORKFLOW_STARTED', 'DISCOVERY_COMPLETED', 'USER_CONTEXT_REQUIRED', 'CONTEXT_PROVIDED', 'PLAN_CREATED', 'PLAN_APPROVED', 'PLAN_CHANGE_REQUESTED', 'CONTEXT_REQUIRED', 'IMPLEMENTATION_COMPLETED', 'REVIEW_PASSED', 'REVIEW_FIX_REQUIRED', 'REVIEW_CONTEXT_REQUIRED')),
    from_state TEXT,
    to_state TEXT,
    plan_version INTEGER,
    payload TEXT CHECK (payload IS NULL OR json_valid(payload)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflow(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_event_workflow ON workflow_event(workflow_id, id);
CREATE INDEX IF NOT EXISTS idx_workflow_event_type ON workflow_event(workflow_id, event_type);

CREATE VIEW IF NOT EXISTS latest_artifact AS
SELECT a.* FROM artifact a JOIN (SELECT workflow_id, artifact_type, MAX(rowid) AS max_rowid FROM artifact GROUP BY workflow_id, artifact_type) latest ON latest.max_rowid = a.rowid;

CREATE VIEW IF NOT EXISTS workflow_status_view AS
SELECT w.id AS workflow_id, w.task, w.session_id, w.project_path, w.current_state, w.current_plan_version, w.approved_plan_version, w.created_at, w.updated_at, w.completed_at,
 (SELECT id FROM artifact WHERE workflow_id = w.id AND artifact_type = 'CONTEXT' ORDER BY rowid DESC LIMIT 1) AS latest_context_id,
 (SELECT id FROM artifact WHERE workflow_id = w.id AND artifact_type = 'PLAN' ORDER BY rowid DESC LIMIT 1) AS latest_plan_id,
 (SELECT id FROM artifact WHERE workflow_id = w.id AND artifact_type = 'APPROVAL' ORDER BY rowid DESC LIMIT 1) AS latest_approval_id,
 (SELECT id FROM artifact WHERE workflow_id = w.id AND artifact_type = 'IMPLEMENTATION' ORDER BY rowid DESC LIMIT 1) AS latest_implementation_id,
 (SELECT id FROM artifact WHERE workflow_id = w.id AND artifact_type = 'REVIEW' ORDER BY rowid DESC LIMIT 1) AS latest_review_id
FROM workflow w;
