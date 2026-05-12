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


def test_transcribe_endpoint(client, monkeypatch):
    """The /transcribe endpoint shells out to asr.transcribe; stub it for speed."""
    import asr

    def fake_transcribe(audio_path):
        return {
            "semanticLabel": "fake",
            "segments": [
                {"startTime": 0.1, "endTime": 0.5, "text": "fˈeɪk", "semanticLabel": "fake"}
            ],
            "language": "en",
            "languageProbability": 1.0,
        }

    monkeypatch.setattr(asr, "transcribe", fake_transcribe)

    clip_id = client.get("/api/clips").get_json()[0]["id"]
    res = client.post(f"/api/clips/{clip_id}/transcribe")
    assert res.status_code == 200
    body = res.get_json()
    assert body["semanticLabel"] == "fake"
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == "fˈeɪk"


def test_agreement_needs_two_annotators(client):
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    res = client.get(f"/api/clips/{clip_id}/agreement")
    assert res.status_code == 200
    body = res.get_json()
    assert body["pairs"] == []
    assert "note" in body


def test_agreement_two_users_identical(client):
    """Two annotators with identical segments → κ=1.0, F1=1.0, PER=0."""
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    segs = [
        {"startTime": 0.0, "endTime": 1.0, "text": "ðə", "semanticLabel": "the"},
        {"startTime": 1.0, "endTime": 2.0, "text": "kæt", "semanticLabel": "cat"},
    ]
    import json as _json

    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=_json.dumps(segs),
        content_type="application/json",
    )
    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=_json.dumps(segs),
        content_type="application/json",
        headers={"Remote-User": "alice"},
    )

    res = client.get(f"/api/clips/{clip_id}/agreement")
    assert res.status_code == 200
    pairs = res.get_json()["pairs"]
    assert len(pairs) == 1
    p = pairs[0]
    assert p["frameKappa"] == 1.0
    assert p["boundaryF1"] == 1.0
    assert p["phonemeErrorRate"] == 0.0
    assert p["matchedSegmentCount"] == 2


def test_agreement_two_users_disagree(client):
    """Different IPA on same boundaries → κ<1, boundary F1=1, PER>0."""
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    import json as _json

    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=_json.dumps(
            [{"startTime": 0.0, "endTime": 1.0, "text": "ðə", "semanticLabel": "the"}]
        ),
        content_type="application/json",
    )
    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=_json.dumps(
            [{"startTime": 0.0, "endTime": 1.0, "text": "dʌ", "semanticLabel": "the"}]
        ),
        content_type="application/json",
        headers={"Remote-User": "alice"},
    )
    res = client.get(f"/api/clips/{clip_id}/agreement").get_json()
    p = res["pairs"][0]
    assert p["boundaryF1"] == 1.0
    assert p["phonemeErrorRate"] > 0
    assert p["frameKappa"] is not None and p["frameKappa"] < 1.0


def test_corpus_agreement(client):
    clip_id = client.get("/api/clips").get_json()[0]["id"]
    import json as _json

    payload = [{"startTime": 0.0, "endTime": 1.0, "text": "ðə", "semanticLabel": "the"}]
    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=_json.dumps(payload),
        content_type="application/json",
    )
    client.put(
        f"/api/clips/{clip_id}/annotations",
        data=_json.dumps(payload),
        content_type="application/json",
        headers={"Remote-User": "alice"},
    )

    res = client.get("/api/agreement")
    body = res.get_json()
    assert len(body["pairs"]) == 1
    assert body["pairs"][0]["clipsShared"] == 1
    assert body["pairs"][0]["frameKappa"] == 1.0


def test_transcribe_missing_clip(client):
    res = client.post("/api/clips/99999/transcribe")
    assert res.status_code == 404


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
