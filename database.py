from __future__ import annotations

import atexit
import os
import re
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).parent
DEFAULT_SQLITE_PATH = ROOT / "data" / "command-center.db"

# Local development reads .env; hosted environments provide these variables
# through their settings. Values are deliberately never logged.
load_dotenv(ROOT / ".env", override=False)


class DatabaseUnavailable(RuntimeError):
    pass


class HybridRow(dict[str, Any]):
    """Mapping row that retains sqlite.Row-compatible numeric indexing."""

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _as_row(value: Any) -> HybridRow | sqlite3.Row | None:
    if value is None or isinstance(value, sqlite3.Row):
        return value
    if isinstance(value, Mapping):
        return HybridRow(value)
    raise TypeError(f"Unsupported database row type: {type(value).__name__}")


class CursorAdapter:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def lastrowid(self) -> int | None:
        return getattr(self._cursor, "lastrowid", None)

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    def fetchone(self) -> HybridRow | sqlite3.Row | None:
        return _as_row(self._cursor.fetchone())

    def fetchall(self) -> list[HybridRow | sqlite3.Row]:
        result: list[HybridRow | sqlite3.Row] = []
        for value in self._cursor.fetchall():
            row = _as_row(value)
            if row is not None:
                result.append(row)
        return result

    def __iter__(self) -> Iterator[HybridRow | sqlite3.Row]:
        for value in self._cursor:
            row = _as_row(value)
            if row is not None:
                yield row


def _replace_qmark_parameters(statement: str) -> str:
    output: list[str] = []
    single_quoted = False
    double_quoted = False
    index = 0
    while index < len(statement):
        character = statement[index]
        if character == "'" and not double_quoted:
            output.append(character)
            if single_quoted and index + 1 < len(statement) and statement[index + 1] == "'":
                output.append("'")
                index += 2
                continue
            single_quoted = not single_quoted
        elif character == '"' and not single_quoted:
            double_quoted = not double_quoted
            output.append(character)
        elif character == "?" and not single_quoted and not double_quoted:
            output.append("%s")
        else:
            output.append(character)
        index += 1
    return "".join(output)


def postgres_statement(statement: str) -> str:
    translated, replacements = re.subn(
        r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
        "INSERT INTO",
        statement,
        flags=re.IGNORECASE,
    )
    translated = _replace_qmark_parameters(translated)
    if replacements and "ON CONFLICT" not in translated.upper():
        stripped = translated.rstrip()
        suffix = ";" if stripped.endswith(";") else ""
        if suffix:
            stripped = stripped[:-1].rstrip()
        translated = f"{stripped} ON CONFLICT DO NOTHING{suffix}"
    return translated


class ConnectionAdapter:
    def __init__(self, connection: Any, backend: str):
        self._connection = connection
        self.backend = backend

    def execute(self, statement: str, parameters: Sequence[Any] | None = None) -> CursorAdapter:
        query = postgres_statement(statement) if self.backend == "postgresql" else statement
        cursor = self._connection.execute(query, tuple(parameters or ()))
        return CursorAdapter(cursor)

    def executemany(self, statement: str, parameters: Iterable[Sequence[Any]]) -> CursorAdapter:
        query = postgres_statement(statement) if self.backend == "postgresql" else statement
        cursor = self._connection.cursor()
        cursor.executemany(query, parameters)
        return CursorAdapter(cursor)

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self._connection.executescript(script)
            return
        for statement in (part.strip() for part in script.split(";")):
            if statement:
                self._connection.execute(statement)


def configured_database_url() -> str | None:
    override = os.getenv("NORTHSTAR_DATABASE_URL")
    if override:
        return None if override.lower() in {"sqlite", "sqlite3"} else override
    return os.getenv("DATABASE_URL") or os.getenv("DB_CRED")


def database_backend() -> str:
    url = configured_database_url()
    if url and url.startswith(("postgres://", "postgresql://")):
        return "postgresql"
    return "sqlite"


_pool: Any = None


def _postgres_pool() -> Any:
    global _pool
    if _pool is not None:
        return _pool
    url = configured_database_url()
    if not url:
        raise DatabaseUnavailable("PostgreSQL is selected but no database URL is configured")
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise DatabaseUnavailable("PostgreSQL support is not installed; install requirements.txt") from exc
    try:
        maximum = max(1, int(os.getenv("NORTHSTAR_DB_POOL_MAX", "5")))
    except ValueError as exc:
        raise DatabaseUnavailable("NORTHSTAR_DB_POOL_MAX must be an integer") from exc
    _pool = ConnectionPool(
        conninfo=url,
        min_size=0,
        max_size=maximum,
        open=False,
        kwargs={"autocommit": False, "connect_timeout": 10, "row_factory": dict_row},
    )
    _pool.open(wait=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(close_pool)


@contextmanager
def connection() -> Iterator[ConnectionAdapter]:
    backend = database_backend()
    if backend == "sqlite":
        DEFAULT_SQLITE_PATH.parent.mkdir(exist_ok=True)
        raw = sqlite3.connect(DEFAULT_SQLITE_PATH)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        adapter = ConnectionAdapter(raw, backend)
        try:
            yield adapter
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return

    pool = _postgres_pool()
    try:
        raw = pool.getconn(timeout=10)
    except Exception as exc:
        raise DatabaseUnavailable("Unable to connect to the configured PostgreSQL database") from exc
    adapter = ConnectionAdapter(raw, backend)
    try:
        yield adapter
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        pool.putconn(raw)


def database_health() -> dict[str, str]:
    backend = database_backend()
    try:
        with connection() as con:
            con.execute("SELECT 1 AS healthy").fetchone()
        return {"engine": "PostgreSQL" if backend == "postgresql" else "SQLite", "status": "Connected"}
    except Exception:
        return {"engine": "PostgreSQL" if backend == "postgresql" else "SQLite", "status": "Unavailable"}
