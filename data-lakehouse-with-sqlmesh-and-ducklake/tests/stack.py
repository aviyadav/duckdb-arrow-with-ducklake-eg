"""Helpers for tests that need the local Data Lab stack (RustFS, PostgreSQL, DuckDB)."""

import socket

import pytest

from shared.settings import env


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def s3_reachable() -> bool:
    endpoint = env.str("S3_ENDPOINT")
    host, _, port = endpoint.rpartition(":")

    return _reachable(host.strip("[]") or "localhost", int(port))


def postgres_reachable() -> bool:
    return _reachable(
        env.str("PSQL_CATALOG_HOST"),
        env.int("PSQL_CATALOG_PORT"),
    )


requires_stack = pytest.mark.skipif(
    not (s3_reachable() and postgres_reachable()),
    reason="RustFS and/or PostgreSQL are not reachable",
)
