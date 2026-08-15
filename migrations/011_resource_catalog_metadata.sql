ALTER TABLE study_resources ADD COLUMN provider_title TEXT NOT NULL DEFAULT '';
ALTER TABLE study_resources ADD COLUMN test_reference TEXT;
ALTER TABLE study_resources ADD COLUMN category TEXT;
ALTER TABLE study_resources ADD COLUMN tags TEXT NOT NULL DEFAULT '';
ALTER TABLE study_resources ADD COLUMN cat_priority TEXT NOT NULL DEFAULT 'MEDIUM';
ALTER TABLE study_resources ADD COLUMN cat_core INTEGER NOT NULL DEFAULT 1 CHECK (cat_core IN (0, 1));

CREATE INDEX IF NOT EXISTS idx_study_resources_search_title ON study_resources(title, provider, test_reference);
CREATE INDEX IF NOT EXISTS idx_study_resources_catalog_filters ON study_resources(active, subject, type, difficulty, free, cat_core);
