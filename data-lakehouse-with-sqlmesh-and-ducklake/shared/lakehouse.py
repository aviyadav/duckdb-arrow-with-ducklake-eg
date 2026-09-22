import json
import os
from pathlib import Path
from typing import Optional

import duckdb
from loguru import logger as log

from shared.settings import LOCAL_DIR, env
from shared.storage import Storage, StoragePrefix
from shared.tools import generate_init_sql


class LakehouseException(Exception):
    pass


class Lakehouse:
    """DuckDB engine on top of the DuckLake catalogs.

    Connect with `read_only=False` when writing to the lakehouse, since the engine
    database is shared with the SQLMesh state.
    """

    def __init__(self, in_memory: bool = False, read_only: bool = True):
        if in_memory:
            log.info("Connecting to DuckDB: in-memory")
            self.conn = duckdb.connect()
        else:
            engine_db = os.path.join(LOCAL_DIR, env.str("ENGINE_DB"))
            log.info("Connecting to DuckDB: {}", engine_db)
            self.conn = duckdb.connect(engine_db, read_only=read_only)

        log.info("Initializing lakehouse with init SQL")

        try:
            init_sql = generate_init_sql()
            self.conn.execute(init_sql)
        except Exception as e:
            raise LakehouseException(f"Error executing init SQL: {e}")

        self.storage = Storage(prefix=StoragePrefix.EXPORTS)

    # Exporting
    # =========

    def export(self, catalog: str, schema: str) -> str:
        s3_export_path = self.storage.get_dir(f"{catalog}/{schema}", dated=True)

        log.info("Exporting {}.{} to {}", catalog, schema, s3_export_path)

        tables = self.conn.execute(
            """
            SELECT
                table_catalog,
                table_name
            FROM
                information_schema.tables
            WHERE
                table_catalog = ?
                AND table_schema = ?
            ORDER BY
                table_name
            """,
            (catalog, schema),
        ).fetchall()

        log.info(
            "Found {} tables in {}.{} for exporting",
            len(tables),
            catalog,
            schema,
        )

        for database, name in tables:
            if "nodes" in name:
                path = f"{s3_export_path}/nodes/{name}.parquet"
            elif "edges" in name:
                path = f"{s3_export_path}/edges/{name}.parquet"
            else:
                path = f"{s3_export_path}/{name}.parquet"

            table_fqn = f"{database}.{schema}.{name}"

            log.info("Exporting {} to {}", table_fqn, path)

            try:
                self.conn.execute(f"COPY {table_fqn} TO '{path}' (FORMAT parquet)")
            except Exception as e:
                raise LakehouseException(f"Could not export {table_fqn}: {e}")

        self.storage.upload_manifest(f"{catalog}/{schema}", latest=s3_export_path)

        log.info("Export completed: {}", s3_export_path)

        return s3_export_path

    def latest_export(self, catalog: str, schema: str) -> Optional[str]:
        manifest = self.storage.load_manifest(f"{catalog}/{schema}")

        if manifest is None:
            return

        if "latest" not in manifest:
            log.warning("No latest field found in manifest")
            return

        return manifest["latest"]

    # Ingestion
    # =========

    def copy_into(self, catalog: str, schema: str, table_name: str, from_path: str):
        log.info("Loading into {}.{}.{}: {}", catalog, schema, table_name, from_path)

        suffix = Path(from_path).suffix.lstrip(".")

        if suffix not in ("parquet", "csv"):
            raise ValueError(f"file type not supported: {suffix}")

        self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

        self.conn.execute(
            f"""
            CREATE OR REPLACE TABLE {catalog}.{schema}.{table_name} AS
            SELECT * FROM '{from_path}'
            """
        )

    # Information
    # ===========

    def snapshot_id(self, catalog: str) -> int:
        log.info("Querying snapshot_id (version) for {} catalog", catalog)

        rel = self.conn.sql(
            f"""--sql
            SELECT max(snapshot_id) AS snapshot_id
            FROM "{catalog}".snapshots()
            """
        )

        snapshot_id = rel.to_df()["snapshot_id"].item()

        return snapshot_id

    def snapshot_changes(self, catalog: str, limit: int = 10) -> list[dict]:
        log.info("Reading last {} snapshot changes for {} catalog", limit, catalog)

        # DuckLake keeps the changelog in the `changes` column of snapshots(), rather
        # than behind a `snapshot_changes()` function.
        rel = self.conn.sql(
            f"""--sql
            SELECT
                snapshot_id,
                snapshot_time,
                changes
            FROM "{catalog}".snapshots()
            ORDER BY snapshot_id DESC
            LIMIT {limit}
            """
        )

        return json.loads(rel.to_df().to_json(orient="records", date_format="iso"))

    def schema(
        self,
        catalog: str,
        schema: str,
        table_name: str,
    ) -> list[dict[str, str]]:
        log.info("Reading schema for {}.{}.{}", catalog, schema, table_name)

        self.conn.execute(
            f"""--sql
            SELECT *
            FROM "{catalog}"."{schema}"."{table_name}"
            LIMIT 0
            """
        )

        schema = [dict(name=desc[0], type=desc[1]) for desc in self.conn.description]

        return schema

    def count(
        self,
        catalog: str,
        schema: str,
        table_name: str,
        where: str | None = None,
    ) -> int:
        log.info("Counting rows in for {}.{}.{}", catalog, schema, table_name)

        query = f"""--sql
            SELECT count(*)
            FROM "{catalog}"."{schema}"."{table_name}"
        """

        if where is not None:
            query += f"""--sql
                WHERE {where}
            """

        self.conn.execute(query)

        count = self.conn.fetchone()[0]

        return count
