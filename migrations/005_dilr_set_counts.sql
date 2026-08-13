ALTER TABLE task_results ADD COLUMN dilr_sets_solved INTEGER NOT NULL DEFAULT 0 CHECK (dilr_sets_solved >= 0);
