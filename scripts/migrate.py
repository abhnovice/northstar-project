import sqlite3
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"
import main


def report():
    with sqlite3.connect(main.DB_PATH) as con:
        versions = [row[0] for row in con.execute("SELECT version FROM schema_migrations ORDER BY version")]
        resources = con.execute("SELECT COUNT(*) FROM study_resources").fetchone()[0]
        mappings = con.execute("SELECT COUNT(*) FROM topic_resource_maps").fetchone()[0]
        access = con.execute("SELECT COUNT(*) FROM user_resource_access").fetchone()[0]
        assignments = con.execute("SELECT COUNT(*) FROM task_resource_assignments").fetchone()[0]
        results = con.execute("SELECT COUNT(*) FROM task_results").fetchone()[0]
        events = con.execute("SELECT COUNT(*) FROM topic_performance_events").fetchone()[0]
        revisions = con.execute("SELECT COUNT(*) FROM revision_schedule WHERE status='PENDING'").fetchone()[0]
        aimcats = con.execute("SELECT COUNT(*) FROM aimcat_schedules").fetchone()[0]
        historical_aimcats = con.execute("SELECT COUNT(*) FROM aimcat_schedules WHERE historical=1 AND converted_to_additional=0").fetchone()[0]
    print(f"Applied migrations: {', '.join(versions)}")
    print(f"Study resources: {resources}; topic mappings: {mappings}; access settings: {access}")
    print(f"Task material assignments: {assignments}; recorded task results: {results}")
    print(f"Topic performance events: {events}; pending spaced revisions: {revisions}")
    print(f"AIMCAT windows: {aimcats}; historical library: {historical_aimcats}")


if __name__ == "__main__":
    main.init_db()
    report()
