"""End-to-end tests for the Phase-2 IPA Labeler API."""

from __future__ import annotations

import io
import json


def test_index(client):
    assert client.get("/").status_code == 200


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json() == {"ok": True}


def test_me_creates_user(client):
    res = client.get("/api/me")
    assert res.status_code == 200
    body = res.get_json()
    assert body["sub"] == "testuser"
    assert body["id"] >= 1


def test_clips_seeded_from_disk(client):
    res = client.get("/api/clips")
    assert res.status_code == 200
    body = res.get_json()
    assert len(body) == 1
    assert body[0]["originalFilename"] == "harvard.wav"


def test_clip_audio_streams(client):
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    res = client.get(f"/api/clips/{clip_id}/audio")
    assert res.status_code == 200


def test_annotation_roundtrip(client):
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    assert client.get(f"/api/clips/{clip_id}/annotations?user=me").get_json() is None

    payload = [
        {"startTime": 0.1, "endTime": 0.4, "text": "ə", "semanticLabel": "a"},
        {"startTime": 0.5, "endTime": 0.9, "text": "k", "semanticLabel": "k"},
    ]
    res = client.put(
        f"/api/clips/{clip_id}/annotations",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    saved = res.get_json()
    assert len(saved["segments"]) == 2

    fetched = client.get(f"/api/clips/{clip_id}/annotations?user=me").get_json()
    assert fetched["segments"] == saved["segments"]


def test_annotation_rejects_invalid_segments(client):
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    res = client.put(
        f"/api/clips/{clip_id}/annotations",
        data=json.dumps([{"startTime": 1.0, "endTime": 0.5, "text": "x"}]),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_upload_dedupes_by_sha256(client):
    audio_bytes = open(client.application.config["UPLOAD_FOLDER"] / "harvard.wav", "rb").read()
    res = client.post(
        "/api/clips",
        data={"audio": (io.BytesIO(audio_bytes), "different-name.wav", "audio/wav")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200  # dedupe response
    body = res.get_json()
    assert body["duplicate"] is True

    clips = client.get("/api/clips").get_json()
    assert len(clips) == 1


def test_upload_accepts_new_audio(client):
    res = client.post(
        "/api/clips",
        data={"audio": (io.BytesIO(b"RIFF\x00\x00\x00\x00WAVEfresh-bytes"), "new.wav", "audio/wav")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["originalFilename"] == "new.wav"
    assert client.get("/api/clips").status_code == 200


def test_upload_rejects_bad_extension(client):
    res = client.post(
        "/api/clips",
        data={"audio": (io.BytesIO(b"<html>"), "evil.html")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400


def test_upload_rejects_traversal(client):
    res = client.post(
        "/api/clips",
        data={"audio": (io.BytesIO(b"fake"), "../../etc/passwd")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400


def test_multi_user_isolation(client):
    """testuser's annotation must not appear in another user's `user=me` query."""
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=json.dumps([{"startTime": 0, "endTime": 1, "text": "a", "semanticLabel": ""}]),
        content_type="application/json",
    )

    res = client.get(
        f"/api/clips/{clip_id}/annotations?user=me",
        headers={"Remote-User": "alice", "Remote-Email": "alice@x", "Remote-Name": "Alice"},
    )
    assert res.get_json() is None

    res_all = client.get(
        f"/api/clips/{clip_id}/annotations?user=all",
        headers={"Remote-User": "alice"},
    )
    bodies = res_all.get_json()
    assert len(bodies) == 1
    assert bodies[0]["userDisplayName"] == "testuser"


def test_export_json(client):
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    payload = [{"startTime": 0, "endTime": 1, "text": "k", "semanticLabel": ""}]
    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=json.dumps(payload),
        content_type="application/json",
    )
    res = client.get(f"/api/clips/{clip_id}/export/json")
    assert res.status_code == 200
    assert json.loads(res.data) == payload
