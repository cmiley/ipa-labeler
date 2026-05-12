"""Pytest fixtures.

Each test runs against a dedicated Postgres database (`ipa_labeler_test`) so
dev data is never touched. The database is created on first use; tables are
dropped and recreated before every test for a clean slate.

Requires Postgres reachable at IPA_LABELER_TEST_DB_URL (default matches the
local Colima container started for dev).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import psycopg

DEFAULT_TEST_DB_URL = "postgresql://ipa:ipa@127.0.0.1:5432/ipa_labeler_test"
ADMIN_DB_URL = "postgresql://ipa:ipa@127.0.0.1:5432/postgres"


def _ensure_test_database() -> str:
    url = os.environ.get("IPA_LABELER_TEST_DB_URL", DEFAULT_TEST_DB_URL)
    dbname = url.rsplit("/", 1)[-1]
    admin_url = os.environ.get("IPA_LABELER_TEST_ADMIN_URL", ADMIN_DB_URL)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{dbname}"')
    return url


# Set env BEFORE importing the app: db.engine is created at module load.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = _ensure_test_database()
os.environ.setdefault("IPA_LABELER_DEV_USER", "testuser")
os.environ["IPA_LABELER_AUTO_MIGRATE"] = "0"  # we manage tables manually in fixture

import pytest  # noqa: E402

import db  # noqa: E402
import models  # noqa: E402, F401  # ensure tables register on Base.metadata
import app as app_module  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    uploads = data_dir / "uploads"
    uploads.mkdir(parents=True)

    project_root = Path(__file__).resolve().parents[1]
    shutil.copy2(project_root / "harvard.wav", uploads / "harvard.wav")

    monkeypatch.setenv("IPA_LABELER_DATA_DIR", str(data_dir))

    db.Base.metadata.drop_all(db.engine)
    db.Base.metadata.create_all(db.engine)

    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
