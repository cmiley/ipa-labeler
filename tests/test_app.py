import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    (tmp_path / "annotations.json").write_text("{}")

    import importlib
    import app as app_module
    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_index(client):
    assert client.get("/").status_code == 200


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json() == {"ok": True}


def test_upload_rejects_missing_file(client):
    res = client.post("/upload", data={})
    assert res.status_code == 400


def test_upload_rejects_bad_extension(client):
    data = {"audio": (io.BytesIO(b"<html></html>"), "evil.html")}
    res = client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Unsupported file type" in res.get_json()["error"]


def test_upload_rejects_path_traversal(client):
    data = {"audio": (io.BytesIO(b"fake"), "../../etc/passwd")}
    res = client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 400


def test_upload_accepts_wav(client):
    data = {"audio": (io.BytesIO(b"RIFFfake"), "sample.wav", "audio/wav")}
    res = client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["filename"] == "sample.wav"
    assert (Path.cwd() / "uploads" / "sample.wav").exists()


def test_annotations_roundtrip(client):
    payload = [{"text": "ə", "semanticLabel": "a", "startTime": 0.0, "endTime": 0.3}]

    assert client.get("/annotations/foo.wav").get_json() == []

    res = client.post(
        "/annotations/foo.wav",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.get_json() == {"status": "saved"}

    assert client.get("/annotations/foo.wav").get_json() == payload


def test_export_json(client):
    payload = [{"text": "k", "semanticLabel": "", "startTime": 0.1, "endTime": 0.2}]
    client.post(
        "/annotations/clip.wav",
        data=json.dumps(payload),
        content_type="application/json",
    )

    res = client.get("/export/clip.wav/json")
    assert res.status_code == 200
    assert json.loads(res.data) == payload
