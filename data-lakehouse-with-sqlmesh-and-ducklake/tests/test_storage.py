import os

import pytest
from botocore.exceptions import ClientError

from shared.storage import Storage, StoragePrefix
from shared.utils import fn_sanitize
from tests.stack import requires_stack

TEST_DATASET = "datalab_pytest"


def test_fn_sanitize():
    assert fn_sanitize("HR_edges") == "hr_edges"
    assert fn_sanitize("user-listening-history") == "user_listening_history"
    assert fn_sanitize("Million Song, Dataset!") == "million_song_dataset"


def test_get_dir_is_dated():
    storage = Storage(prefix=StoragePrefix.INGEST)

    dated = storage.get_dir("my_dataset", dated=True)
    undated = storage.get_dir("my_dataset")

    assert dated.startswith("s3://")
    assert "/raw/my_dataset/" in dated
    assert undated.startswith("s3://")
    assert undated.endswith("/raw/my_dataset")


def test_s3_path_roundtrip():
    storage = Storage(prefix=StoragePrefix.INGEST)

    s3_path = storage.get_dir("my_dataset", dated=True)

    assert storage.to_s3_path(storage.from_s3_path(s3_path)) == s3_path


@requires_stack
def test_manifest_roundtrip_list_and_clear(tmp_path):
    storage = Storage(prefix=StoragePrefix.INGEST)

    assert storage.exists()

    s3_dir_path = storage.get_dir(
        TEST_DATASET, dated=True, upload_placeholder=True
    )

    data_file = tmp_path / "test.csv"
    data_file.write_text("a,b\n1,2\n", encoding="utf-8")
    storage.upload_file(str(data_file), f"{s3_dir_path}/test.csv")

    storage.upload_manifest(TEST_DATASET, latest=s3_dir_path)

    manifest = storage.load_manifest(TEST_DATASET)

    assert manifest["dataset"] == TEST_DATASET
    assert manifest["latest"] == s3_dir_path

    listing = storage.ls(display=False)
    assert listing[TEST_DATASET] == [f"{storage.from_s3_path(s3_dir_path)}/test.csv"]

    storage.bucket.objects.filter(Prefix=f"raw/{TEST_DATASET}").delete()

    with pytest.raises(ClientError):
        storage.client.head_object(
            Bucket=storage.bucket_name, Key=f"raw/{TEST_DATASET}/manifest.json"
        )


@requires_stack
def test_latest_to_env():
    storage = Storage(prefix=StoragePrefix.INGEST)

    storage.latest_to_env()

    variable = "RAW__DEEZER_SOCIAL_NETWORKS__HR__HR_EDGES"

    assert os.environ[variable].endswith("HR/HR_edges.csv")
