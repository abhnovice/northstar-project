CREATE TABLE IF NOT EXISTS study_resources (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL,
    topic_slug TEXT,
    type TEXT NOT NULL,
    url TEXT,
    platform_path TEXT,
    free INTEGER NOT NULL DEFAULT 0 CHECK (free IN (0, 1)),
    requires_subscription INTEGER NOT NULL DEFAULT 0 CHECK (requires_subscription IN (0, 1)),
    estimated_minutes INTEGER,
    recommended_question_count INTEGER,
    difficulty TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    last_verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topic_resource_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES study_resources(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    phase TEXT NOT NULL DEFAULT 'ALL',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic_id, resource_id, purpose, phase)
);

CREATE TABLE IF NOT EXISTS user_resource_access (
    resource_provider TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    subscription_name TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_study_resources_provider ON study_resources(provider);
CREATE INDEX IF NOT EXISTS idx_study_resources_subject_topic ON study_resources(subject, topic_slug);
CREATE INDEX IF NOT EXISTS idx_topic_resource_maps_topic ON topic_resource_maps(topic_id, purpose, priority);
CREATE INDEX IF NOT EXISTS idx_topic_resource_maps_resource ON topic_resource_maps(resource_id);
