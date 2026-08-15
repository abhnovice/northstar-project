# Northstar — MBA Preparation Command Center

A persistent CAT 2026 + GMAT + ISB preparation operating system built with:

- React 19 + TypeScript + Vite for the frontend
- FastAPI + Python for the backend and adaptive planner
- Managed PostgreSQL for durable application persistence
- Recharts for performance analytics

The app is seeded for the profile and preparation period beginning August 12, 2026. It includes the dynamic six-hour evening plan, mock-day replacement schedule, curriculum trackers, mocks, error lessons, revisions, calendar, deadlines, GMAT, ISB achievement stories, resources, analytics, weekly review, profile and settings.

## Quick start

Requirements: Python 3.11+, Node.js 20+, the dependencies from `requirements.txt` and `package.json`, and `DATABASE_URL` or the existing `DB_CRED` configured in `.env`.

```bash
./run.sh
```

The launcher only starts the Vite frontend and FastAPI backend. Activate whichever Python environment you want before running it.

Optional controls:

```bash
FRONTEND_PORT=5174 BACKEND_PORT=8080 ./run.sh
```

Open the React application at [http://127.0.0.1:5173/ui/](http://127.0.0.1:5173/ui/). The API runs at `http://127.0.0.1:8000`.

Interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Vite proxies `/api` requests to FastAPI. Press `Ctrl+C` in the launcher terminal to stop both servers.

## Deploy on Render

Create a **Python 3 Web Service**, configure `DATABASE_URL` (or `DB_CRED`) as a secret environment variable, and use these commands:

```text
Build Command: pip install -r requirements.txt && npm ci && npm run build
Start Command: ./run_on_render.sh
```

`run_on_render.sh` starts the production FastAPI server on Render's `PORT` and
serves the already-built React app from `static/ui`. It intentionally does not
start the Vite development server.

Northstar uses managed PostgreSQL, so hosted changes survive service restarts and redeploys without relying on Render's ephemeral application filesystem. The connection string is read at runtime and is never shown in the UI.

## Tests

```bash
python -m unittest discover -s tests -v
npm test
npm run lint
npm run typecheck
npm run validate:resources
npm run build
```

The tests exercise resource access, assignment and replacement, task results, mastery progression, spaced revisions, mock/error adaptation, DILR/VARC analytics, coverage, mock-day replacement, and production SPA delivery.

## Database migration and backup

PostgreSQL is the normal runtime database whenever `DATABASE_URL` or `DB_CRED` is configured. SQLite remains a deliberate fallback only when neither variable exists, or when tests set `NORTHSTAR_DATABASE_URL=sqlite`.

The verified pre-migration SQLite backup is retained locally at `backups/command-center-pre-postgres-2026-08-15.db`; the tracked working copy remains at `data/command-center.db`. SQLite has not been deleted. Keep the backup until the PostgreSQL deployment has been manually confirmed.

Run additive SQLite migrations, preview the PostgreSQL transfer, apply it, and verify PostgreSQL with:

```bash
NORTHSTAR_DATABASE_URL=sqlite python scripts/migrate.py
python scripts/migrate_sqlite_to_postgres.py --source backups/command-center-pre-postgres-2026-08-15.db --dry-run
python scripts/migrate_sqlite_to_postgres.py --source backups/command-center-pre-postgres-2026-08-15.db --apply
python scripts/verify_postgres.py
```

The migration is transactional, preserves IDs, checks every migrated table, validates foreign keys/unique keys/non-null columns, and records a source fingerprint so the exact backup can be rerun safely without duplication. It never prints the connection string.

## Study-resource system

The study-material catalogue is connected directly to generated tasks and the adaptive planner.

- Open **Settings → Study Material / Subscriptions** to enable or disable providers.
- Rodha, 2IIM, CAT PYQs via 2IIM, and GMAT Official Prep are enabled by default.
- T.I.M.E. AIMCAT is enabled for the purchased series. IMS SimCAT Plus, VARC1000, and Career Launcher CDC remain disabled until you confirm access.
- `study_resources` stores provider links, platform paths, access requirements, difficulty, and verification dates.
- `topic_resource_maps` connects QA, DILR, and VARC topics to LEARN, PRACTICE, and PYQ purposes.
- `user_resource_access` stores availability independently from the resource catalogue.
- `task_resource_assignments` stores the selected Learn, Practice, and PYQ stage while preserving manual overrides. Replace Material searches the full catalogue; unavailable providers are opt-in to view and cannot be selected.
- `topic_resource_preferences` changes future selection only when its checkbox is explicitly selected.
- `topic_performance_events` stores performance evidence; lesson completion alone never marks a topic strong.
- `revision_schedule` stores additive spaced-revision dates.
- Public URLs and annual course names are seed data in `seeds/resource_catalog.py`, not React constants. Update that file for a new annual default; edits already stored in the database are preserved because seeds use insert-only semantics.

Run additive migrations manually with:

```bash
python scripts/migrate.py
```

Run the development-time coverage audit with:

```bash
npm run validate:resources
```

It fails if an active CAT topic lacks required Learn/Practice/PYQ coverage or the official GMAT diagnostic is unavailable.

## Planning algorithm

Daily Quant selection uses an explicit score:

```text
priority = topic importance
         + mastery gap
         + accuracy gap
         + revision overdue boost
         + mock/error signal boost
         + unfinished-foundation boost
         + time-since-practice boost
```

Practice accuracy and confidence control progression through:

```text
FOUNDATION → INTERMEDIATE → CAT LEVEL → TIMED → MIXED
```

Low performance schedules early recall and smaller repair work. Stronger performance removes unnecessary concept stages and introduces CAT-level, timed, and mixed work. DILR results additionally track solve rate, median time, representation, and selectability. VARC results and error-log entries are normalized into recurring error patterns. Future autogenerated assignments can be retargeted by mock/error evidence, but manual tasks and manually replaced material are never rewritten.

The generated order is:

1. Weak, high-value foundational topics
2. Due revisions
3. Recurring DILR and VARC practice
4. Mock and sectional readiness
5. Lower-priority enrichment

Scheduled T.I.M.E. AIMCATs are the Priority A full-mock backbone; the planner does not independently create weekly generic mocks. Each chosen date replaces the standard timetable with 2 hours testing, 3 hours analysis and 1 hour re-solving. The 1–3 days beforehand taper new learning, and completed AIMCAT diagnosis directs repair work using the latest result, rolling-three evidence, and repeated errors. Historical pre–August 12 AIMCATs remain in a separate library and never create backlog. November 19–29 is protected as CAT Consolidation. Manual tasks, attempt-date overrides, rescheduled analysis, and manually replaced material are preserved.

The T.I.M.E. portal URL is configurable under Settings. Northstar opens it in a new tab and never attempts to sign in.

## Important implementation notes

- Official deadlines are visually distinct from personal targets and are never silently altered.
- Calendar search covers tasks, topics, provider material and test references. Completing a future curriculum task early records its original/actual dates and reuses the slot only with a comparable movable task; mocks, deadlines, manual, locked, pinned, started and prerequisite tasks are protected.
- Resource URLs are seeded in the database and editable through the Resources screen.
- The GMAT retake interval is intentionally a configurable verification note, not a hard-coded rule.
- Admissions-school tags are planning labels, not claims of admission likelihood.
- The frontend defaults to the real current date. Use the date picker in Today to inspect the seeded August 2026 starter week.
