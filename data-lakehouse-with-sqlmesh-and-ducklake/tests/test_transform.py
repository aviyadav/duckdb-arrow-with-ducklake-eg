"""The SQLMesh project loads, keeps the original model names, and audits every model."""

from pathlib import Path

import pytest
from sqlmesh.core.context import Context

from shared.settings import catalog_specs
from transform.config import NOT_FOUND, build_variables, referenced_variables

TRANSFORM_DIR = Path(__file__).parents[1] / "transform"

EXPECTED_MODELS = {
    # stage
    "stage.dsn.hr_edges",
    "stage.dsn.hr_genres",
    "stage.dsn.hu_edges",
    "stage.dsn.hu_genres",
    "stage.dsn.ro_edges",
    "stage.dsn.ro_genres",
    "stage.msdsl.music_info",
    "stage.msdsl.user_listening_history",
    "stage.taoec.countries",
    "stage.taoec.hs92_products",
    "stage.taoec.hs92_ccp_trade",
    "stage.dd.dataset",
    "stage.dd.monitor",
    # marts: graphs
    "graphs.music_taste.dsn_nodes_users",
    "graphs.music_taste.msdsl_nodes_tracks",
    "graphs.music_taste.msdsl_nodes_users",
    "graphs.music_taste.nodes_genres",
    "graphs.music_taste.dsn_edges_friendships",
    "graphs.music_taste.dsn_edges_user_genres",
    "graphs.music_taste.msdsl_edges_track_tags",
    "graphs.music_taste.msdsl_edges_user_tracks",
    "graphs.econ_comp.nodes_countries",
    "graphs.econ_comp.nodes_products",
    "graphs.econ_comp.edges_exports",
    "graphs.econ_comp.edges_imports",
    "graphs.econ_comp.edges_competes_with",
    # marts: analytics
    "analytics.taoec.cc_metrics",
    "analytics.taoec.hs92_ccp_trade_3y_latest",
    "analytics.taoec.competing_countries",
    "analytics.taoec.competing_countries_products",
}

VIEW_MODELS = {
    "analytics.taoec.hs92_ccp_trade_3y_latest",
    "analytics.taoec.competing_countries",
    "analytics.taoec.competing_countries_products",
}

MODELS_WITHOUT_AUDITS = {
    "stage.dd.dataset",
    "stage.dd.monitor",
}


@pytest.fixture(scope="module")
def models() -> dict:
    return {model.name: model for model in Context(paths=str(TRANSFORM_DIR)).models.values()}


def test_project_loads_every_model(models: dict):
    assert set(models) == EXPECTED_MODELS


def test_model_names_keep_the_dbt_catalog_and_schema(models: dict):
    """Names carry over from the dbt project: <catalog>.<schema>.<table>."""
    catalogs = {catalog.alias for catalog in catalog_specs()}

    for name, model in models.items():
        assert name.split(".")[0] in catalogs
        assert model.catalog is not None


def test_audits_cover_every_model_that_dbt_tested(models: dict):
    """SQLMesh audits replace the dbt tests, model for model."""
    without_audits = {
        name for name, model in models.items() if not model.audits_with_args
    }

    # Only the depression detection stage models were untested in the dbt project.
    assert without_audits == MODELS_WITHOUT_AUDITS


def test_view_models_keep_the_dbt_materialization(models: dict):
    views = {name for name, model in models.items() if model.kind.name == "VIEW"}

    assert views == VIEW_MODELS


def test_batch_models_are_full_kind(models: dict):
    kinds = {model.kind.name for model in models.values()}

    assert kinds == {"FULL", "VIEW"}


def test_referenced_raw_variables_are_seeded():
    referenced = referenced_variables()
    variables = build_variables()

    assert referenced
    assert set(variables) >= referenced

    for name in referenced:
        assert name.startswith("RAW__")
        assert variables[name]


def test_unset_raw_variables_fall_back_to_a_placeholder(monkeypatch):
    for name in referenced_variables():
        monkeypatch.delenv(name, raising=False)

    assert set(build_variables().values()) == {NOT_FOUND}
