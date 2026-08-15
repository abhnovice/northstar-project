"""Non-destructive PostgreSQL smoke/CRUD verification without logging credentials."""

from __future__ import annotations

import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import close_pool, connection, database_backend, database_health


def main() -> None:
    if database_backend() != "postgresql":
        raise SystemExit("PostgreSQL is not selected by the current environment")
    health = database_health()
    if health["status"] != "Connected":
        raise SystemExit("PostgreSQL health check failed")
    print("PostgreSQL health: connected", flush=True)
    close_pool()

    resource_id = f"verification-{uuid.uuid4().hex}"
    try:
        with connection() as con:
            con.execute(
                """INSERT INTO study_resources(
                       id,provider,title,description,subject,type,free,requires_subscription,active
                   ) VALUES(?,'USER','Database verification','Temporary CRUD probe','QA','OTHER',1,0,1)""",
                (resource_id,),
            )
        print("Create committed", flush=True)
        close_pool()
        with connection() as con:
            created = con.execute(
                "SELECT title FROM study_resources WHERE id=?", (resource_id,)
            ).fetchone()
            if not created:
                raise RuntimeError("Create did not persist across connections")
            con.execute(
                "UPDATE study_resources SET title='Database verification updated' WHERE id=?",
                (resource_id,),
            )
        print("Read and update committed", flush=True)
        close_pool()
        with connection() as con:
            updated = con.execute(
                "SELECT title FROM study_resources WHERE id=?", (resource_id,)
            ).fetchone()
            if not updated or updated["title"] != "Database verification updated":
                raise RuntimeError("Update did not persist across connections")
            con.execute("DELETE FROM study_resources WHERE id=?", (resource_id,))
        print("Delete committed", flush=True)
        close_pool()
        with connection() as con:
            if con.execute("SELECT 1 FROM study_resources WHERE id=?", (resource_id,)).fetchone():
                raise RuntimeError("Delete did not persist across connections")
    finally:
        with connection() as con:
            con.execute("DELETE FROM study_resources WHERE id=?", (resource_id,))
        close_pool()

    print("PostgreSQL health and create/update/delete persistence across pool restarts passed.")


if __name__ == "__main__":
    main()
