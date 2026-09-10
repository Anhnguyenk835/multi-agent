import hashlib
import os
from pathlib import Path

import psycopg

MIGRATION_LOCK_ID = 834_927_101
DEFAULT_MIGRATION_DIR = Path(__file__).resolve().parents[2] / "migrations"


def apply_migrations(database_url: str, migration_dir: Path = DEFAULT_MIGRATION_DIR) -> None:
    migration_files = sorted(migration_dir.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No migrations found in {migration_dir}")

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("select pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        try:
            connection.execute(
                """
                create table if not exists schema_migrations (
                    version text primary key,
                    checksum text not null,
                    applied_at timestamptz not null default now()
                )
                """
            )
            for migration_file in migration_files:
                sql = migration_file.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                existing = connection.execute(
                    "select checksum from schema_migrations where version = %s",
                    (migration_file.name,),
                ).fetchone()
                if existing:
                    if existing[0] != checksum:
                        raise RuntimeError(f"Migration checksum changed: {migration_file.name}")
                    continue

                with connection.transaction():
                    connection.execute(sql)
                    connection.execute(
                        "insert into schema_migrations(version, checksum) values (%s, %s)",
                        (migration_file.name, checksum),
                    )
        finally:
            connection.execute("select pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))


def main() -> None:
    database_url = os.getenv(
        "BACKEND_DATABASE_URL",
        "postgresql://dashboard:dashboard@localhost:54321/dashboard",
    )
    apply_migrations(database_url)


if __name__ == "__main__":
    main()
