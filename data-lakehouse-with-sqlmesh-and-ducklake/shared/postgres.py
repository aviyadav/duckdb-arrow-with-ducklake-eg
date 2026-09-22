"""PostgreSQL helpers for the DuckLake metadata catalog.

DuckLake creates its own metadata schema on the first `ATTACH`, but the PostgreSQL
database itself has to exist beforehand. That is the one piece of infrastructure the
SQLite backend used to provide for free, so it is handled explicitly here.
"""

import psycopg
from loguru import logger as log

from shared.settings import env


def admin_dsn() -> str:
    return (
        f"host={env.str('PSQL_CATALOG_HOST')} "
        f"port={env.str('PSQL_CATALOG_PORT')} "
        f"user={env.str('PSQL_CATALOG_USER')} "
        f"password={env.str('PSQL_CATALOG_PASSWORD')} "
        f"dbname=postgres"
    )


def catalog_dsn() -> str:
    return (
        f"host={env.str('PSQL_CATALOG_HOST')} "
        f"port={env.str('PSQL_CATALOG_PORT')} "
        f"user={env.str('PSQL_CATALOG_USER')} "
        f"password={env.str('PSQL_CATALOG_PASSWORD')} "
        f"dbname={env.str('PSQL_CATALOG_DB')}"
    )


def catalog_exists() -> bool:
    database = env.str("PSQL_CATALOG_DB")

    with psycopg.connect(admin_dsn(), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()

    return exists is not None


def create_catalog() -> bool:
    """Create the DuckLake metadata database. Returns False when it already exists."""
    database = env.str("PSQL_CATALOG_DB")

    if catalog_exists():
        log.info("Catalog database already exists: {}", database)
        return False

    log.info("Creating catalog database: {}", database)

    with psycopg.connect(admin_dsn(), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{database}"')

    return True
