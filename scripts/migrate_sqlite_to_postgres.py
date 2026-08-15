from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "command-center.db"
SCHEMA_FILE = ROOT / "migrations" / "postgres" / "001_initial_schema.sql"

TABLE_ORDER = [
    "profile", "settings", "topics", "deadlines", "resources", "stories", "day_reviews",
    "study_resources", "user_resource_access", "time_foundation_tests", "aimcat_schedules",
    "mocks", "tasks", "errors", "schema_migrations", "topic_resource_maps",
    "task_resource_assignments", "task_results", "topic_performance_events",
    "revision_schedule", "adaptive_signals", "plan_days", "task_reschedule_history",
    "time_foundation_attempts", "task_early_completion_history", "topic_resource_preferences",
    "time_foundation_schedule",
]

FOREIGN_KEYS = [
    ("tasks", "topic_id", "topics", "id"),
    ("tasks", "aimcat_schedule_id", "aimcat_schedules", "id"),
    ("tasks", "time_foundation_test_id", "time_foundation_tests", "id"),
    ("tasks", "reallocated_task_id", "tasks", "id"),
    ("mocks", "aimcat_schedule_id", "aimcat_schedules", "id"),
    ("aimcat_schedules", "mock_id", "mocks", "id"),
    ("topic_resource_maps", "topic_id", "topics", "id"),
    ("topic_resource_maps", "resource_id", "study_resources", "id"),
    ("task_resource_assignments", "task_id", "tasks", "id"),
    ("task_resource_assignments", "resource_id", "study_resources", "id"),
    ("task_results", "task_id", "tasks", "id"),
    ("topic_performance_events", "topic_id", "topics", "id"),
    ("revision_schedule", "topic_id", "topics", "id"),
    ("revision_schedule", "source_task_id", "tasks", "id"),
    ("adaptive_signals", "topic_id", "topics", "id"),
    ("task_reschedule_history", "task_id", "tasks", "id"),
    ("time_foundation_attempts", "test_id", "time_foundation_tests", "id"),
    ("time_foundation_attempts", "task_id", "tasks", "id"),
    ("task_early_completion_history", "completed_task_id", "tasks", "id"),
    ("task_early_completion_history", "replacement_task_id", "tasks", "id"),
    ("topic_resource_preferences", "topic_id", "topics", "id"),
    ("topic_resource_preferences", "resource_id", "study_resources", "id"),
    ("time_foundation_schedule", "test_id", "time_foundation_tests", "id"),
    ("time_foundation_schedule", "task_id", "tasks", "id"),
]

UNIQUE_KEYS = [
    ("aimcat_schedules", ("test_ref",)),
    ("time_foundation_tests", ("test_reference",)),
    ("topic_resource_maps", ("topic_id", "resource_id", "purpose", "phase")),
    ("task_resource_assignments", ("task_id", "stage")),
    ("task_results", ("task_id",)),
    ("topic_performance_events", ("topic_id", "source_type", "source_id")),
    ("topic_resource_preferences", ("topic_id", "stage")),
    ("time_foundation_schedule", ("test_id",)),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely migrate Northstar SQLite data to PostgreSQL.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="SQLite source file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate connectivity and print the migration plan")
    mode.add_argument("--apply", action="store_true", help="Apply schema and data in one transaction")
    parser.add_argument("--allow-nonempty", action="store_true", help="Permit first migration into matching non-empty Northstar tables")
    return parser.parse_args()


def database_url() -> str:
    values = dotenv_values(ROOT / ".env")
    value = (
        os.getenv("DATABASE_URL") or os.getenv("DB_CRED")
        or values.get("DATABASE_URL") or values.get("DB_CRED")
    )
    if not value or not value.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("A PostgreSQL DATABASE_URL or DB_CRED is required in .env")
    return value


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise RuntimeError(f"SQLite source does not exist: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        con.close()
        raise RuntimeError("SQLite integrity check failed")
    return con


def source_tables(con: sqlite3.Connection) -> list[str]:
    existing = {
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    }
    return [table for table in TABLE_ORDER if table in existing]


def source_counts(con: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    return {table: int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) for table in tables}


def schema_statements() -> list[str]:
    return [statement.strip() for statement in SCHEMA_FILE.read_text(encoding="utf-8").split(";") if statement.strip()]


def target_columns(cursor: Any, table: str) -> list[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    return [row[0] for row in cursor.fetchall()]


def source_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]


def primary_key(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")') if row[5]]


def migrate_table(source: sqlite3.Connection, target: Any, table: str) -> int:
    from psycopg import sql

    target_names = set(target_columns(target, table))
    columns = [name for name in source_columns(source, table) if name in target_names]
    keys = primary_key(source, table)
    if not columns or not keys:
        raise RuntimeError(f"Cannot determine migratable columns/primary key for {table}")
    rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
    if not rows:
        return 0
    non_keys = [column for column in columns if column not in keys]
    update = sql.SQL(",").join(
        sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in non_keys
    )
    conflict = sql.SQL("DO UPDATE SET ") + update if non_keys else sql.SQL("DO NOTHING")
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) ").format(
        sql.Identifier(table),
        sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(sql.Placeholder() for _ in columns),
        sql.SQL(",").join(map(sql.Identifier, keys)),
    ) + conflict
    target.executemany(statement, [tuple(row[column] for column in columns) for row in rows])
    return len(rows)


def reset_identity(target: Any, table: str) -> None:
    from psycopg import sql

    target.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
    row = target.fetchone()
    if not row or not row[0]:
        return
    target.execute(
        sql.SQL("SELECT setval(%s, COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM {}").format(sql.Identifier(table)),
        (row[0],),
    )


def verify_counts(source: sqlite3.Connection, target: Any, tables: list[str]) -> list[tuple[str, int, int]]:
    summary = []
    for table in tables:
        sqlite_count = int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        target.execute(f'SELECT COUNT(*) FROM "{table}"')
        postgres_count = int(target.fetchone()[0])
        summary.append((table, sqlite_count, postgres_count))
    return summary


def verify_source_keys(source: sqlite3.Connection, target: Any, tables: list[str]) -> int:
    """Allow target-side additions while proving every source identity survived."""
    from psycopg import sql

    missing = 0
    for table in tables:
        keys = primary_key(source, table)
        if not keys:
            continue
        source_keys = {
            tuple(row[key] for key in keys)
            for row in source.execute(f'SELECT * FROM "{table}"')
        }
        target.execute(
            sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(",").join(map(sql.Identifier, keys)), sql.Identifier(table)
            )
        )
        target_keys = {tuple(row) for row in target.fetchall()}
        missing += len(source_keys - target_keys)
    return missing


def verify_relations(target: Any, tables: set[str]) -> int:
    from psycopg import sql

    orphans = 0
    for child, child_column, parent, parent_column in FOREIGN_KEYS:
        if child not in tables or parent not in tables:
            continue
        query = sql.SQL(
            "SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{child_col}=p.{parent_col} "
            "WHERE c.{child_col} IS NOT NULL AND p.{parent_col} IS NULL"
        ).format(
            child=sql.Identifier(child), parent=sql.Identifier(parent),
            child_col=sql.Identifier(child_column), parent_col=sql.Identifier(parent_column),
        )
        target.execute(query)
        orphans += int(target.fetchone()[0])
    return orphans


def verify_duplicates(target: Any, tables: set[str]) -> int:
    from psycopg import sql

    duplicates = 0
    for table, columns in UNIQUE_KEYS:
        if table not in tables:
            continue
        grouped = sql.SQL(",").join(map(sql.Identifier, columns))
        target.execute(
            sql.SQL("SELECT COUNT(*) FROM (SELECT {} FROM {} GROUP BY {} HAVING COUNT(*)>1) duplicate_rows").format(
                grouped, sql.Identifier(table), grouped,
            )
        )
        duplicates += int(target.fetchone()[0])
    return duplicates


def verify_nulls(target: Any, tables: set[str]) -> int:
    from psycopg import sql

    target.execute(
        "SELECT table_name,column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND is_nullable='NO'"
    )
    required = [(table, column) for table, column in target.fetchall() if table in tables]
    violations = 0
    for table, column in required:
        target.execute(
            sql.SQL("SELECT COUNT(*) FROM {} WHERE {} IS NULL").format(sql.Identifier(table), sql.Identifier(column))
        )
        violations += int(target.fetchone()[0])
    return violations


def print_summary(summary: list[tuple[str, int, int]], orphans: int, duplicates: int, nulls: int, missing: int) -> None:
    width = max(len(table) for table, _, _ in summary)
    for table, sqlite_count, postgres_count in summary:
        print(f"{table:<{width}}  SQLite {sqlite_count:<5} PostgreSQL {postgres_count}")
    print(f"orphan foreign keys: {orphans}")
    print(f"duplicate unique keys: {duplicates}")
    print(f"null violations: {nulls}")
    print(f"missing SQLite primary keys: {missing}")


def main() -> int:
    args = parse_args()
    source_path = args.source.resolve()
    source = source_connection(source_path)
    tables = source_tables(source)
    counts = source_counts(source, tables)
    source_hash = fingerprint(source_path)
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt before running the migration") from exc

    print("Source SQLite integrity: ok")
    print(f"Source tables: {len(tables)}; source rows: {sum(counts.values())}")
    print("Target: managed PostgreSQL (credentials hidden)")
    with psycopg.connect(database_url(), connect_timeout=10) as postgres:
        with postgres.cursor() as target:
            target.execute("SELECT 1")
            print("Target connection: ok")
            if not args.apply:
                target.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
                print(f"Dry run only; target currently has {target.fetchone()[0]} public tables. No changes made.")
                return 0

            target.execute("SELECT pg_advisory_xact_lock(hashtext('northstar_sqlite_migration'))")
            for statement in schema_statements():
                target.execute(statement)
            target.execute("SELECT 1 FROM migration_audits WHERE source_fingerprint=%s", (source_hash,))
            if target.fetchone():
                summary = verify_counts(source, target, tables)
                table_set = set(tables)
                print("This exact SQLite backup was already migrated; no rows were written.")
                orphans = verify_relations(target, table_set)
                duplicates = verify_duplicates(target, table_set)
                nulls = verify_nulls(target, table_set)
                missing = verify_source_keys(source, target, tables)
                print_summary(summary, orphans, duplicates, nulls, missing)
                if orphans or duplicates or nulls or missing:
                    raise RuntimeError("Existing migration verification failed")
                postgres.rollback()
                return 0

            target_nonempty = []
            for table in tables:
                target.execute(f'SELECT COUNT(*) FROM "{table}"')
                if target.fetchone()[0]:
                    target_nonempty.append(table)
            if target_nonempty and not args.allow_nonempty:
                postgres.rollback()
                raise RuntimeError(
                    "Target already contains Northstar rows. Re-run with --allow-nonempty only after reviewing the target."
                )

            target.execute("SET CONSTRAINTS ALL DEFERRED")
            for table in tables:
                migrate_table(source, target, table)
                if "id" in source_columns(source, table):
                    reset_identity(target, table)

            summary = verify_counts(source, target, tables)
            table_set = set(tables)
            orphans = verify_relations(target, table_set)
            duplicates = verify_duplicates(target, table_set)
            nulls = verify_nulls(target, table_set)
            missing = verify_source_keys(source, target, tables)
            if any(sqlite_count != postgres_count for _, sqlite_count, postgres_count in summary):
                raise RuntimeError("Row-count verification failed; transaction rolled back")
            if orphans or duplicates or nulls or missing:
                raise RuntimeError("Relational verification failed; transaction rolled back")
            target.execute(
                "INSERT INTO migration_audits(source_fingerprint,source_path,source_tables,source_rows) VALUES(%s,%s,%s,%s)",
                (source_hash, source_path.name, len(tables), sum(counts.values())),
            )
            print_summary(summary, orphans, duplicates, nulls, missing)
        postgres.commit()
    source.close()
    print("Migration committed. SQLite source and backup were not modified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Migration failed safely: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
