"""Seed object storage with the small Music Taste fixtures.

The real datasets are large Kaggle downloads, so this is the quickest way to run the
whole pipeline (ingest -> transform -> export) end to end without Kaggle credentials:

    python -m tests.seed
"""

import tempfile
from pathlib import Path

from tests.fixtures import (
    COUNTRIES,
    upload_fixtures,
    write_deezer_fixtures,
    write_msdsl_fixtures,
)

DEEZER_DATASET = "deezer_social_networks"
MSDSL_DATASET = "million_song_dataset_spotify_lastfm"


def seed(source_dir: Path) -> dict[str, str]:
    write_deezer_fixtures(source_dir / DEEZER_DATASET)
    write_msdsl_fixtures(source_dir / MSDSL_DATASET)

    deezer_files = []

    for country in COUNTRIES:
        country_dir = source_dir / DEEZER_DATASET / country

        deezer_files.append(
            (f"{country}/{country}_edges.csv", country_dir / f"{country}_edges.csv")
        )
        deezer_files.append(
            (f"{country}/{country}_genres.json", country_dir / f"{country}_genres.json")
        )

    msdsl_dir = source_dir / MSDSL_DATASET

    return {
        DEEZER_DATASET: upload_fixtures(DEEZER_DATASET, deezer_files),
        MSDSL_DATASET: upload_fixtures(
            MSDSL_DATASET,
            [
                ("music_info.csv", msdsl_dir / "music_info.csv"),
                ("user_listening_history.csv", msdsl_dir / "user_listening_history.csv"),
            ],
        ),
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        for dataset, s3_path in seed(Path(tmp_dir)).items():
            print(f"{dataset}: {s3_path}")
