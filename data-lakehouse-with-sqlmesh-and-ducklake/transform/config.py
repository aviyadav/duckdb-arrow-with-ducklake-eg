"""SQLMesh configuration for the Data Lab transform layer.

The project is a rewrite of the original dbt project: models keep the same
catalog/schema/table names, DuckLake catalogs are still attached to DuckDB, and
PostgreSQL is still the DuckLake metadata backend. What changes is who runs the
transformations (SQLMesh instead of dbt) and who stores the objects (RustFS).
"""

import os
import re
from pathlib import Path

from sqlmesh.core.config import Config, GatewayConfig, ModelDefaultsConfig
from sqlmesh.core.config.common import VirtualEnvironmentMode
from sqlmesh.core.config.connection import DuckDBAttachOptions, DuckDBConnectionConfig

from shared.settings import LOCAL_DIR, catalog_specs, env

PROJECT_DIR = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_DIR / "models"

RAW_VARIABLE_PREFIX = "RAW__"
RAW_VARIABLE_PATTERN = re.compile(rf"{RAW_VARIABLE_PREFIX}[A-Z0-9_]+")

# dbt used `env_var(name, 'NOT_FOUND')` for datasets that had not been ingested yet.
NOT_FOUND = "NOT_FOUND"


def ducklake_metadata_path() -> str:
    """DuckLake metadata lives in PostgreSQL, so the attach path carries the libpq DSN.

    Using the DSN keeps every catalog self-contained: no extra DuckDB secret has to
    exist before a catalog can be attached.
    """
    return (
        "ducklake:postgres:"
        f"dbname={env.str('PSQL_CATALOG_DB')} "
        f"host={env.str('PSQL_CATALOG_HOST')} "
        f"port={env.str('PSQL_CATALOG_PORT')} "
        f"user={env.str('PSQL_CATALOG_USER')} "
        f"password={env.str('PSQL_CATALOG_PASSWORD')}"
    )


def build_catalogs() -> dict[str, DuckDBAttachOptions]:
    catalogs = {
        # The first entry becomes the default catalog, which is also where SQLMesh
        # keeps its own state schema.
        "engine": DuckDBAttachOptions(
            type="duckdb",
            path=os.path.join(LOCAL_DIR, env.str("ENGINE_DB")),
        )
    }

    bucket = env.str("S3_BUCKET")

    for catalog in catalog_specs():
        catalogs[catalog.alias] = DuckDBAttachOptions(
            type="ducklake",
            path=ducklake_metadata_path(),
            metadata_schema=catalog.metadata_schema,
            data_path=f"s3://{bucket}/{catalog.s3_prefix}",
            encrypted=catalog.encrypted,
        )

    return catalogs


def build_secrets() -> dict[str, dict[str, str]]:
    return {
        "rustfs": {
            "type": "s3",
            "key_id": env.str("S3_ACCESS_KEY_ID"),
            "secret": env.str("S3_SECRET_ACCESS_KEY"),
            "endpoint": env.str("S3_ENDPOINT"),
            "use_ssl": str(env.bool("S3_USE_SSL", default=True)).lower(),
            "url_style": env.str("S3_URL_STYLE"),
            "region": env.str("S3_REGION"),
        }
    }


def referenced_variables() -> set[str]:
    """Every RAW__* variable referenced by a model.

    SQLMesh has to render each model before it can build the DAG, so a model whose
    variable is missing breaks the whole project, even for a scoped run. Referenced
    variables are therefore seeded with a placeholder and only resolve to a real
    object storage path once the dataset has been ingested.
    """
    names = set()

    for path in MODELS_DIR.rglob("*.sql"):
        names.update(RAW_VARIABLE_PATTERN.findall(path.read_text(encoding="utf-8")))

    return names


def build_variables() -> dict[str, str]:
    """Expose the RAW__* variables pointing at the latest ingested datasets.

    dlctl resolves ingested datasets from their manifests before SQLMesh is invoked,
    so a new ingestion changes the variables and SQLMesh re-renders the affected models.
    """
    variables = {name: NOT_FOUND for name in referenced_variables()}

    variables.update(
        {
            name: value
            for name, value in os.environ.items()
            if name.startswith(RAW_VARIABLE_PREFIX)
        }
    )

    return variables


connection = DuckDBConnectionConfig(
    catalogs=build_catalogs(),
    extensions=["httpfs", "parquet", "postgres", "ducklake"],
    secrets=build_secrets(),
    # Column descriptions stay in SQLMesh metadata (and the rendered DAG) instead of
    # being pushed to the catalog as comments, which DuckLake only accepts on tables.
    register_comments=False,
)

config = Config(
    gateways={
        "lakehouse": GatewayConfig(
            connection=connection,
            variables=build_variables(),
        )
    },
    default_gateway="lakehouse",
    model_defaults=ModelDefaultsConfig(
        dialect="duckdb",
        kind="FULL",
    ),
    # The transform layer is a batch pipeline, so every run is a full refresh.
    default_target_environment="prod",
    # Publish prod models as DuckLake tables under their model name, rather than as
    # views on top of a hidden physical layer.
    virtual_environment_mode=VirtualEnvironmentMode.DEV_ONLY,
)
