-- Trankil-v2 — schéma SQLite (spec §4.1)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT,
    stored_path TEXT NOT NULL,
    mime_type TEXT,
    file_hash TEXT,
    created_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('pro', 'perso')),
    date_emission DATE NOT NULL,
    date_event DATE,
    deadline DATE,
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'urgent', 'archived')),
    completed_at DATETIME,
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    raw_summary TEXT,
    justification_proof TEXT,
    suggestion TEXT,
    recurrence_pattern TEXT CHECK (
        recurrence_pattern IS NULL
        OR recurrence_pattern IN ('daily', 'weekly', 'monthly')
    ),
    parent_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    calendar_synced INTEGER NOT NULL DEFAULT 0,
    calendar_event_id TEXT,
    created_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

CREATE TABLE IF NOT EXISTS notifications_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL CHECK (notification_type IN ('j_minus_3', 'j_minus_1')),
    sent_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (task_id, notification_type)
);

CREATE TABLE IF NOT EXISTS email_reminders_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    reminder_date DATE NOT NULL,
    sent_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (task_id, reminder_date)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Index de performance (spec §4.3)
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_documents_stored_path ON documents(stored_path);
CREATE INDEX IF NOT EXISTS idx_tasks_raw_summary ON tasks(raw_summary);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);

-- Paramètres par défaut (spec §4.1)
INSERT OR IGNORE INTO settings (key, value) VALUES ('ollama_model', 'llama3.2-vision');
INSERT OR IGNORE INTO settings (key, value) VALUES ('ollama_base_url', 'http://localhost:11434');
INSERT OR IGNORE INTO settings (key, value) VALUES ('gemini_model', 'gemini-2.5-flash');
INSERT OR IGNORE INTO settings (key, value) VALUES ('gemini_api_key', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('google_calendar_auto_sync', 'false');
INSERT OR IGNORE INTO settings (key, value) VALUES ('notification_enabled', 'true');
INSERT OR IGNORE INTO settings (key, value) VALUES ('email_reminder_enabled', 'true');
INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_server', 'smtp.gmail.com');
INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_port', '587');
INSERT OR IGNORE INTO settings (key, value) VALUES ('sender_email', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('recipient_email', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('email_reminder_last_sent_date', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('autopilot_enabled', 'true');
INSERT OR IGNORE INTO settings (key, value) VALUES ('active_ia_provider', 'Gemini (Natif)');
INSERT OR IGNORE INTO settings (key, value) VALUES ('openrouter_api_key', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('openrouter_model', 'qwen/qwen-2.5-vl-72b-instruct');
