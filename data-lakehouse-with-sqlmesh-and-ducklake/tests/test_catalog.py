import pytest

from shared.lakehouse import Lakehouse
from shared.postgres import catalog_exists, catalog_dsn
from shared.settings import MART_SCHEMAS, catalog_specs
from shared.tools import generate_init_sql
from tests.stack import requires_stack


def test_catalog_specs_cover_every_schema():
    catalogs = {catalog.alias: catalog for catalog in catalog_specs()}

    assert "stage" in catalogs
    assert "secure_stage" in catalogs
    assert catalogs["secure_stage"].encrypted is True

    for mart in MART_SCHEMAS:
        assert mart in catalogs


def test_init_sql_uses_rustfs_and_postgres():
    init_sql = generate_init_sql()

    assert "CREATE OR REPLACE SECRET rustfs" in init_sql
    assert "INSTALL ducklake" in init_sql
    assert "TYPE ducklake" in init_sql

    for catalog in catalog_specs():
        assert f"AS {catalog.metadata_schema}" in init_sql
        assert f"DATA_PATH 's3://" in init_sql


@requires_stack
def test_catalog_database_exists():
    assert catalog_exists()
    assert "dbname=" in catalog_dsn()


@requires_stack
def test_lakehouse_attaches_every_catalog():
    lakehouse = Lakehouse()

    attached = {
        row[0]
        for row in lakehouse.conn.execute(
            "SELECT database_name FROM duckdb_databases()"
        ).fetchall()
    }

    for catalog in catalog_specs():
        assert catalog.alias in attached


@requires_stack
def test_lakehouse_export_roundtrip():
    lakehouse = Lakehouse()

    latest = lakehouse.latest_export("graphs", "music_taste")

    if latest is None:
        pytest.skip("No export found for graphs.music_taste")

    nodes = lakehouse.conn.execute(
        f"SELECT count(*) FROM '{latest}/nodes/*.parquet'"
    ).fetchone()[0]
    edges = lakehouse.conn.execute(
        f"SELECT count(*) FROM '{latest}/edges/*.parquet'"
    ).fetchone()[0]

    assert nodes > 0
    assert edges > 0


@requires_stack
def test_graph_counts_are_consistent():
    """Nodes referenced by edges must exist, which is what the relationship audits check."""
    lakehouse = Lakehouse()

    orphan_friendships = lakehouse.conn.execute(
        """
        SELECT count(*)
        FROM graphs.music_taste.dsn_edges_friendships AS e
        LEFT JOIN graphs.music_taste.dsn_nodes_users AS n
            ON e.source_id = n.node_id
        WHERE n.node_id IS NULL
        """
    ).fetchone()[0]

    assert orphan_friendships == 0


@requires_stack
def test_graph_node_ids_share_one_sequence():
    """Every node model draws from one shared node_id sequence.

    This is the check the original dbt project made with a cross-model singular test.
    """
    lakehouse = Lakehouse()

    duplicate_node_ids = lakehouse.conn.execute(
        """
        WITH all_ids AS (
            SELECT node_id FROM graphs.music_taste.dsn_nodes_users
            UNION ALL
            SELECT node_id FROM graphs.music_taste.msdsl_nodes_tracks
            UNION ALL
            SELECT node_id FROM graphs.music_taste.msdsl_nodes_users
            UNION ALL
            SELECT node_id FROM graphs.music_taste.nodes_genres
        )
        SELECT count(*)
        FROM (
            SELECT node_id
            FROM all_ids
            GROUP BY node_id
            HAVING count(*) > 1
        )
        """
    ).fetchone()[0]

    assert duplicate_node_ids == 0
