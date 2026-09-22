import os
import subprocess
import sys
import tempfile
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Optional

import click
from loguru import logger as log

import shared.tools as T
from dlctl.sqlmesh_handler import DOCS_PORT, SQLMeshHandler
from export.cli import export
from ingest.cli import ingest
from shared.cache import cache_usage, expunge_cache
from shared.postgres import create_catalog
from shared.settings import LOCAL_DIR, MART_SCHEMA_VARS, env
from shared.storage import Storage, StoragePrefix

LOG_FILE = Path(__file__).resolve().parents[1] / "logs/datalab.log"
LOG_FILE_RELATIVE = os.path.relpath(LOG_FILE.resolve(), start=Path.cwd())


@click.group(
    help="Data Lab, by https://youtube.com/@DataLabTechTV",
    invoke_without_command=True,
)
@click.option(
    "--debug",
    is_flag=True,
    help="Globally enable logging debug mode",
)
@click.option(
    "--no-logfile",
    "logfile_enabled",
    is_flag=True,
    default=True,
    help=f"Disable file logging ({LOG_FILE_RELATIVE})",
)
@click.option(
    "--version",
    "show_version",
    is_flag=True,
    help="Show current version for datalab",
)
@click.pass_context
def dlctl(ctx: click.Context, debug: bool, logfile_enabled: bool, show_version: bool):
    if show_version:
        print(f"datalab version {version('datalab')}")
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(1)

    level = "DEBUG" if debug else "INFO"

    log.remove()
    log.add(sys.stderr, level=level)

    if logfile_enabled:
        log.add(LOG_FILE, rotation="10 MB", retention="7 days", level=level)

    log.info("Welcome to Data Lab, by https://youtube.com/@DataLabTechTV")


# External
# ========

dlctl.add_command(ingest)
dlctl.add_command(export)

# Backups
# =======


@dlctl.group(help="Manage catalog backups")
def backup():
    pass


def _export_psql_env():
    os.environ["PGHOST"] = env.str("PSQL_CATALOG_HOST")
    os.environ["PGPORT"] = env.str("PSQL_CATALOG_PORT")
    os.environ["PGDATABASE"] = env.str("PSQL_CATALOG_DB")
    os.environ["PGUSER"] = env.str("PSQL_CATALOG_USER")
    os.environ["PGPASSWORD"] = env.str("PSQL_CATALOG_PASSWORD")


@backup.command(name="create", help="Backup the catalog into object storage")
def backup_create():
    log.info("Creating a catalog backup")

    _export_psql_env()

    with tempfile.NamedTemporaryFile(
        prefix="datalab-lakehouse-",
        suffix=".dump",
    ) as tmp:
        log.debug("Dumping to temporary file: {}", tmp.name)
        subprocess.run(["pg_dump", "-Fc", "-f", tmp.name], check=True)

        s = Storage(prefix=StoragePrefix.BACKUPS)
        s3_backup_path = s.get_dir("catalog", dated=True)
        s.upload_file(tmp.name, f"{s3_backup_path}/lakehouse.dump")
        s.upload_manifest("catalog", latest=s3_backup_path)

        log.info("Catalog backup created: {}", s3_backup_path)


@backup.command(name="restore", help="Restore the catalog into PostgreSQL")
@click.option(
    "--source",
    "source_date",
    type=click.DateTime(formats=["%Y-%m-%dT%H:%M:%S.%f"]),
    help="Timestamp for backup source (YYYY-mm-ddTHH:MM:SS.sss)",
)
def backup_restore(source_date: Optional[datetime]):
    _export_psql_env()

    db = env.str("PSQL_CATALOG_DB")

    s = Storage(prefix=StoragePrefix.BACKUPS)

    if source_date is None:
        manifest = s.load_manifest("catalog")

        if manifest is None or "latest" not in manifest:
            log.error("No catalog backups found in manifest")
            return

        s3_path = manifest["latest"]
    else:
        date = source_date.strftime("%Y_%m_%d")
        time = source_date.strftime("%H_%M_%S_%f")[:-3]
        s3_path = s.to_s3_path(f"{env.str('S3_BACKUPS_PREFIX')}/catalog/{date}/{time}")

    log.info("Restoring backup from {}", s3_path)

    with tempfile.NamedTemporaryFile(
        prefix="datalab-lakehouse-",
        suffix=".dump",
    ) as tmp:
        log.debug("Downloading dump to temporary file: {}", tmp.name)
        s.download_file(f"{s3_path}/lakehouse.dump", tmp.name)

        log.debug("Restoring dump from temporary file: {}", tmp.name)
        subprocess.run(
            ["pg_restore", "-c", "--if-exists", "-d", db, tmp.name],
            check=True,
        )


@backup.command(name="ls", help="List catalog backups")
@click.option(
    "--all",
    "-a",
    "include_all",
    is_flag=True,
    help="Display all files (not only the top-level backup directory)",
)
def backup_ls(include_all: bool):
    log.info("Listing all catalog backups")

    storage = Storage(prefix=StoragePrefix.BACKUPS)

    listing = storage.ls(include_all=True, display=False).get("catalog")

    if listing is None:
        return

    if not include_all:
        listing = set("/".join(path.split("/")[:4]) for path in listing)

    timestamps_displayed = set()

    for path in sorted(listing):
        date, time = path.split("/")[2:4]

        date = date.replace("_", "-")
        time = time.replace("_", ":", 2).replace("_", ".")

        timestamp = f"{date}T{time}"

        if timestamp in timestamps_displayed:
            print(f"{' ' * 23}\t    {path}")
        else:
            if include_all and len(timestamps_displayed) > 0:
                print()

            print(f"{timestamp}\t => {path}")
            timestamps_displayed.add(timestamp)


# Transform
# =========


@dlctl.command(help="Transform datasets (ETL via SQLMesh and DuckDB/DuckLake)")
@click.option(
    "--model",
    "-m",
    "models",
    multiple=True,
    type=click.STRING,
    help="Model to transform (can be used multiple times, supports + selectors)",
)
@click.option("--debug", is_flag=True, help="Run SQLMesh with debug logging")
def transform(models: Optional[tuple[str, ...]], debug: bool):
    sqlmesh_handler = SQLMeshHandler(debug=debug)
    sqlmesh_handler.run(models)


# Test
# ====


@dlctl.command(name="test", help="Run data audits")
@click.option(
    "--model",
    "-m",
    "models",
    multiple=True,
    type=click.STRING,
    help="Model to audit (can be used multiple times)",
)
@click.option("--debug", is_flag=True, help="Run SQLMesh with debug logging")
def test(models: Optional[tuple[str, ...]], debug: bool):
    sqlmesh_handler = SQLMeshHandler(debug=debug)
    sqlmesh_handler.test(models)


# Documentation
# =============


@dlctl.group(name="docs", help="Generate or serve model documentation")
def docs():
    pass


@docs.command(name="generate", help="Generate the model DAG (see local/docs)")
def docs_generate():
    sqlmesh_handler = SQLMeshHandler()
    sqlmesh_handler.docs_generate()


@docs.command(name="serve", help=f"Serve documentation (port {DOCS_PORT})")
@click.option("--port", type=click.INT, default=DOCS_PORT, help="Port to serve on")
def docs_serve(port: int):
    sqlmesh_handler = SQLMeshHandler()
    sqlmesh_handler.docs_serve(port=port)


# Tools
# =====


@dlctl.group(help="Standalone tools for ops and other tasks")
def tools():
    pass


@tools.command(
    help="Generate local/init.sql to be used with duckdb -init",
)
@click.option(
    "--path",
    type=click.STRING,
    default=os.path.join(LOCAL_DIR, "init.sql"),
    help="Custom output path for the init.sql file",
)
def generate_init_sql(path: str):
    T.generate_init_sql(path)


@tools.command(name="create-bucket", help="Create the object storage bucket in RustFS")
def create_bucket():
    storage = Storage(prefix=StoragePrefix.INGEST)
    storage.create()


@tools.command(
    name="init-catalog",
    help="Create the PostgreSQL database used as the DuckLake metadata catalog",
)
def init_catalog():
    created = create_catalog()

    if created:
        log.info("Catalog database created")
    else:
        log.info("Catalog database already exists")


@tools.command(name="catalog-info", help="Show DuckLake catalog information")
def catalog_info():
    from shared.lakehouse import Lakehouse

    lh = Lakehouse()

    for schema in MART_SCHEMA_VARS:
        catalog = env.str(schema)

        log.info("{}: snapshot {}", catalog, lh.snapshot_id(catalog))


# Cache
# =====


@dlctl.group(help="Manage cache (requests, etc.)")
def cache():
    pass


@cache.command(name="clean", help="Expunge cache")
@click.option(
    "-ns",
    "--namespace",
    type=click.Choice(["requests", "huggingface"]),
    help="Limit cache cleaning to a namespace",
)
@click.option(
    "-n",
    "--name",
    type=click.STRING,
    help="Limit cache cleaning to a specific name (namespace required as well)",
)
def cache_clean(namespace: Optional[str], name: Optional[str]):
    if namespace is None and name is not None:
        raise click.UsageError("name requires that namespace is set")

    expunge_cache(namespace, name)


@cache.command(name="df", help="Calculate cache usage statistics")
def cache_df():
    cache_usage()


if __name__ == "__main__":
    dlctl()
