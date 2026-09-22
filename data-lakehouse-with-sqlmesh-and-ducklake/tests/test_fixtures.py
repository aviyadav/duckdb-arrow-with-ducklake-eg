import csv
import json
from pathlib import Path

from tests.fixtures import (
    COUNTRIES,
    GENRES,
    LISTENING_USERS,
    MUSIC_INFO_HEADER,
    MUSIC_INFO_ROWS,
    write_deezer_fixtures,
    write_listening_history,
    write_music_info,
)


def test_music_info_fixture_is_well_formed_csv(tmp_path):
    """Regression: an unquoted tag list used to add a 22nd field to every row."""
    path = tmp_path / "music_info.csv"
    write_music_info(path, count=5)

    header, *data = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))

    assert len(header) == len(MUSIC_INFO_HEADER.split(",")) == 21

    for row in data:
        assert len(row) == len(header)


def test_listening_history_fixture_has_unique_pairs(tmp_path):
    """The msdsl_edges_user_tracks model audits a unique (track_id, user_id) pair."""
    path = tmp_path / "user_listening_history.csv"
    write_listening_history(path, tracks=10, users=5)

    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))[1:]
    pairs = [(row[0], row[1]) for row in rows]

    assert len(pairs) == 50
    assert len(set(pairs)) == 50


def test_deezer_edges_reference_fixture_users(tmp_path):
    """Regression: edge node IDs must match the user IDs in the genres fixture."""
    source_dir = tmp_path / "deezer_social_networks"
    write_deezer_fixtures(source_dir)

    for index, country in enumerate(COUNTRIES):
        base_id = (index + 1) * 1000

        edges = list(
            csv.reader(
                (source_dir / country / f"{country}_edges.csv")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        )[1:]

        genres = json.loads(
            (source_dir / country / f"{country}_genres.json").read_text(
                encoding="utf-8"
            )
        )

        user_ids = set(genres)
        edge_ids = {node for edge in edges for node in edge}

        assert edge_ids == user_ids
        assert len(user_ids) == len(GENRES[country])
        assert all(
            base_id < int(node) <= base_id + len(GENRES[country])
            for node in edge_ids
        )


def test_fixture_sizes_are_large_enough_to_write_parquet():
    """Small tables are inlined by DuckLake, so one fixture must exceed that limit."""
    assert MUSIC_INFO_ROWS * LISTENING_USERS > 1000


def test_write_deezer_fixtures_creates_one_dir_per_country(tmp_path):
    source_dir = tmp_path / "deezer_social_networks"
    write_deezer_fixtures(source_dir)

    assert sorted(p.name for p in source_dir.iterdir()) == sorted(COUNTRIES)

    for country in COUNTRIES:
        assert (source_dir / country / f"{country}_edges.csv").exists()
        assert (source_dir / country / f"{country}_genres.json").exists()
