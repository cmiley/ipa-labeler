from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import zipfile
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, send_file
from sqlalchemy import select

import annotations as annotations_module
import clips as clips_module
from auth import get_or_create_current_user
from db import engine, session_scope
from models import Annotation, AudioClip, Base

SEED_FILES = ["harvard.wav"]


def _data_dir() -> Path:
    return Path(os.environ.get("IPA_LABELER_DATA_DIR", ".")).resolve()


def _seed_disk_files(upload_folder: Path) -> None:
    """Copy bundled sample files into the upload folder on first start."""
    app_dir = Path(__file__).parent.resolve()
    for name in SEED_FILES:
        src = app_dir / name
        dst = upload_folder / name
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _seed_db_from_disk(upload_folder: Path) -> None:
    """Ensure every file in upload_folder has a row in audio_clips.

    Idempotent: matches existing rows by content_sha256, skips temp files.
    Used both for the harvard.wav bootstrap and for the JSON-migration cutover.
    """
    if not upload_folder.exists():
        return
    with session_scope() as session:
        for path in sorted(upload_folder.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            digest = _sha256_path(path)
            existing = session.scalar(select(AudioClip).where(AudioClip.content_sha256 == digest))
            if existing is not None:
                continue
            session.add(
                AudioClip(
                    storage_filename=path.name,
                    original_filename=path.name,
                    content_sha256=digest,
                    uploaded_by=None,
                    status="approved",
                )
            )


def create_app() -> Flask:
    app = Flask(__name__)
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    upload_folder = data_dir / "uploads"
    upload_folder.mkdir(exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

    _seed_disk_files(upload_folder)

    if os.environ.get("IPA_LABELER_AUTO_MIGRATE") == "1":
        Base.metadata.create_all(engine)
    if os.environ.get("IPA_LABELER_AUTO_SEED", "1") == "1":
        _seed_db_from_disk(upload_folder)

    app.register_blueprint(clips_module.bp)
    app.register_blueprint(annotations_module.bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}, 200

    @app.get("/api/me")
    def me():
        with session_scope() as session:
            user = get_or_create_current_user(session)
            return jsonify(user.to_dict())

    @app.post("/api/clips/<int:clip_id>/transcribe")
    def transcribe_clip(clip_id: int):
        from pathlib import Path as _Path

        import asr

        with session_scope() as session:
            clip = session.get(AudioClip, clip_id)
            if clip is None:
                abort(404)
            storage_filename = clip.storage_filename

        audio_path = _Path(app.config["UPLOAD_FOLDER"]) / storage_filename
        if not audio_path.exists():
            abort(404, description="audio file missing on disk")

        try:
            result = asr.transcribe(audio_path)
        except Exception as exc:
            app.logger.exception("transcribe failed for clip %s", clip_id)
            return jsonify({"error": f"transcription failed: {exc}"}), 500

        return jsonify(result)

    @app.get("/api/clips/<int:clip_id>/export/<fmt>")
    def export(clip_id: int, fmt: str):
        with session_scope() as session:
            clip = session.get(AudioClip, clip_id)
            if clip is None:
                abort(404)
            user = get_or_create_current_user(session)
            ann = session.scalar(
                select(Annotation).where(
                    Annotation.clip_id == clip_id, Annotation.user_id == user.id
                )
            )
            segments = ann.segments if ann else []
            storage_filename = clip.storage_filename
            original_stem = Path(clip.original_filename).stem

        if fmt == "json":
            return send_file(
                io.BytesIO(json.dumps(segments, indent=2).encode("utf-8")),
                mimetype="application/json",
                as_attachment=True,
                download_name=f"{original_stem}_annotations.json",
            )
        if fmt == "txt":
            lines = []
            for s in segments:
                line = f"{s['startTime']:.2f}s - {s['endTime']:.2f}s: {s['text']}"
                if s.get("semanticLabel"):
                    line += f" ({s['semanticLabel']})"
                lines.append(line)
            return send_file(
                io.BytesIO("\n".join(lines).encode("utf-8")),
                mimetype="text/plain",
                as_attachment=True,
                download_name=f"{original_stem}_annotations.txt",
            )
        if fmt == "zip":
            buf = io.BytesIO()
            audio_path = upload_folder / storage_filename
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                if audio_path.exists():
                    zf.write(audio_path, clip.original_filename)
                zf.writestr(f"{original_stem}_annotations.json", json.dumps(segments, indent=2))
                lines = []
                for s in segments:
                    line = f"{s['startTime']:.2f}s - {s['endTime']:.2f}s: {s['text']}"
                    if s.get("semanticLabel"):
                        line += f" ({s['semanticLabel']})"
                    lines.append(line)
                zf.writestr(f"{original_stem}_annotations.txt", "\n".join(lines))
            buf.seek(0)
            return send_file(
                buf,
                mimetype="application/zip",
                as_attachment=True,
                download_name=f"{original_stem}_export.zip",
            )
        return jsonify({"error": "Invalid format"}), 400

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", "5000")))
