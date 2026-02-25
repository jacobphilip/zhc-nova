PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    route_class TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requires_approval INTEGER NOT NULL DEFAULT 0,
    risk_level TEXT NOT NULL DEFAULT 'low',
    assigned_worker TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    action_category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'required',
    requested_by TEXT,
    decided_by TEXT,
    decision_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workers (
    worker_id TEXT PRIMARY KEY,
    worker_type TEXT NOT NULL,
    host TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    capabilities_json TEXT,
    last_seen_at TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_dispatch_lease (
    task_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    lease_status TEXT NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT NOT NULL,
    heartbeat_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_route_class ON tasks(route_class);
CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_task_id ON artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_lease_status_expiry ON task_dispatch_lease(lease_status, lease_expires_at);
