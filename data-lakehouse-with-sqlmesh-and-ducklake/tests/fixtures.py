"""Fixture data for the Music Taste graph.

The real datasets (Deezer social networks, Million Song Dataset) are large third
party downloads, so the fixtures reproduce their exact shape with a small number of
rows, including one table that is big enough to be written as parquet files by
DuckLake instead of being inlined in the catalog.
"""

import json
from pathlib import Path

from shared.storage import Storage, StoragePrefix

COUNTRIES = ("HR", "HU", "RO")

# User and edge node IDs are small integers, exactly like the published datasets:
# Deezer files use 1..N per country, and the model prefixes them per country.
EDGES = [(1, 2), (2, 3), (3, 1), (1, 3), (3, 4), (4, 2)]

GENRES = {
    "HR": {"1": ["Pop"], "2": ["Dance", "Pop", "Rock"], "3": ["Rock"], "4": ["Jazz"]},
    "HU": {
        "1": ["Jazz"],
        "2": ["Dance", "International Pop"],
        "3": ["Pop"],
        "4": ["Rock"],
    },
    "RO": {
        "1": ["Rap/Hip Hop"],
        "2": ["Pop", "Rock"],
        "3": ["Jazz"],
        "4": ["Pop"],
    },
}

EDGES_HEADER = "node_1,node_2"
MUSIC_INFO_HEADER = (
    "track_id,name,artist,spotify_preview_url,spotify_id,tags,genre,year,"
    "duration_ms,danceability,energy,key,loudness,mode,speechiness,acousticness,"
    "instrumentalness,liveness,valence,tempo,time_signature"
)
LISTENING_HISTORY_HEADER = "track_id,user_id,playcount"

TRACK_TAGS = ["dance_pop", "rock", "jazz", "international_pop", "rap_hip_hop"]

MUSIC_INFO_ROWS = 100
LISTENING_USERS = 50
LISTENING_HISTORY_ROWS = MUSIC_INFO_ROWS * LISTENING_USERS


def track_id(index: int) -> str:
    return f"TRXXXX{index:08d}"


def write_edges(path: Path, base_id: int, edges: list[tuple[int, int]]):
    lines = [EDGES_HEADER]

    for source, target in edges:
        lines.append(f"{base_id + source},{base_id + target}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_genres(path: Path, genres: dict[str, list[str]]):
    path.write_text(json.dumps(genres), encoding="utf-8", newline="\n")


def write_music_info(path: Path, count: int = MUSIC_INFO_ROWS):
    rows = [MUSIC_INFO_HEADER]

    for index in range(1, count + 1):
        # The tags list is quoted, exactly like the CSV published on Kaggle.
        tags = ", ".join(TRACK_TAGS[index % len(TRACK_TAGS) :][:2])

        rows.append(
            f"{track_id(index)},Track {index},Artist {index},"
            f"https://p.scdn.co/mp3-preview/{index},"
            f"spotify:track:{index},"
            f'"{tags}",Pop,{1990 + (index % 30)},'
            f"{180000 + index},0.5,0.7,{index % 12},-5.0,1,0.05,0.1,0.0,0.2,0.6,"
            f"120.0,4"
        )

    path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def write_listening_history(
    path: Path,
    tracks: int = MUSIC_INFO_ROWS,
    users: int = LISTENING_USERS,
):
    """Write one row per user/track pair, as the unique combination the model expects."""
    rows = [LISTENING_HISTORY_HEADER]

    for user in range(1, users + 1):
        for track in range(1, tracks + 1):
            rows.append(f"{track_id(track)},user_{user:03d},{(user * track) % 500 + 1}")

    path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def write_deezer_fixtures(source_dir: Path):
    """Write the Deezer Social Networks fixture files under their country directories."""
    for index, country in enumerate(COUNTRIES):
        country_dir = source_dir / country
        country_dir.mkdir(parents=True, exist_ok=True)

        base_id = (index + 1) * 1000

        write_edges(country_dir / f"{country}_edges.csv", base_id, EDGES)

        genres = {
            str(base_id + int(user_id)): values
            for user_id, values in GENRES[country].items()
        }

        write_genres(country_dir / f"{country}_genres.json", genres)


def write_msdsl_fixtures(source_dir: Path):
    source_dir.mkdir(parents=True, exist_ok=True)

    write_music_info(source_dir / "music_info.csv")
    write_listening_history(source_dir / "user_listening_history.csv")


def upload_fixtures(dataset: str, files: list[tuple[str, Path]]):
    """Upload fixture files into a new dated directory, mirroring a manual ingestion."""
    storage = Storage(prefix=StoragePrefix.INGEST)

    s3_dir_path = storage.get_dir(dataset, dated=True, upload_placeholder=True)

    for relative_path, source_path in files:
        storage.upload_file(str(source_path), f"{s3_dir_path}/{relative_path}")

    storage.upload_manifest(dataset, latest=s3_dir_path)

    return s3_dir_path
