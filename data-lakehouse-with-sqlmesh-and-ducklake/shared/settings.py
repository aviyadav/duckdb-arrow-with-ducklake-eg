import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from environs import Env

# environs keeps .env values private to the Env instance. The lakehouse also relies on
# real environment variables: data mart schemas are discovered by name, and SQLMesh
# reads the RAW__* variables pointing at the latest ingested datasets. Loading the file
# into os.environ as well keeps both access paths in sync.
load_dotenv(find_dotenv())

env = Env()
env.read_env()

LOCAL_DIR = str((Path(__file__).parents[1] / "local").resolve())

MART_SCHEMA_VARS = []
MART_SCHEMAS = []

for varname, value in os.environ.items():
    if varname.endswith("_MART_SCHEMA"):
        MART_SCHEMA_VARS.append(varname)
        MART_SCHEMAS.append(value)


@dataclass(frozen=True)
class Catalog:
    """A DuckLake catalog, identified by the PostgreSQL schema holding its metadata."""

    alias: str
    s3_prefix: str
    metadata_schema: str
    encrypted: bool = False


def catalog_specs() -> list[Catalog]:
    """Read the DuckLake catalog list from the environment.

    Every PSQL_CATALOG_*_SCHEMA variable maps to an S3_*_PREFIX variable holding the
    location of the catalog's managed parquet files, e.g. stage -> S3_STAGE_PREFIX.
    """
    schema_vars = [
        "PSQL_CATALOG_STAGE_SCHEMA",
        "PSQL_CATALOG_SECURE_STAGE_SCHEMA",
    ] + MART_SCHEMA_VARS

    catalogs = []

    for varname in schema_vars:
        basename = varname.removeprefix("PSQL_CATALOG_").removesuffix("_SCHEMA")

        catalogs.append(
            Catalog(
                alias=env.str(varname),
                s3_prefix=env.str(f"S3_{basename}_PREFIX").strip("/"),
                metadata_schema=env.str(varname),
                encrypted=varname == "PSQL_CATALOG_SECURE_STAGE_SCHEMA",
            )
        )

    return catalogs
