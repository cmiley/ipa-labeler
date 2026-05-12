from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory
from sqlalchemy import select
from werkzeug.utils import secure_filename

from auth import get_or_create_current_user
from db import session_scope
from models import Annotation, AudioClip

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".webm"}

bp = Blueprint("clips", __name__, url_prefix="/api/clips")


def _upload_dir() -> Path:
    return current_app.config["UPLOAD_FOLDER"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe_audio(path: Path) -> tuple[float | None, int | None]:
    try:
        import mutagen

        meta = mutagen.File(str(path))  # type: ignore[attr-defined]
        if meta is None or meta.info is None:
            return None, None
        duration = float(meta.info.length) if hasattr(meta.info, "length") else None
        sr = int(getattr(meta.info, "sample_rate", 0)) or None
        return duration, sr
    except Exception:
        return None, None


@bp.get("")
def list_clips():
    """List clips with optional filters.

    Query params:
        filter: 'all' (default) | 'mine_unlabeled' | 'mine_labeled' | 'uploaded_by_me'
    """
    filter_mode = request.args.get("filter", "all")

    with session_scope() as session:
        user = get_or_create_current_user(session)
        q = select(AudioClip).where(AudioClip.status == "approved").order_by(AudioClip.id)

        if filter_mode == "uploaded_by_me":
            q = q.where(AudioClip.uploaded_by == user.id)
        clips = session.scalars(q).all()

        if filter_mode in ("mine_unlabeled", "mine_labeled"):
            labeled_clip_ids = {
                a.clip_id
                for a in session.scalars(
                    select(Annotation).where(Annotation.user_id == user.id)
                )
            }
            if filter_mode == "mine_unlabeled":
                clips = [c for c in clips if c.id not in labeled_clip_ids]
            else:
                clips = [c for c in clips if c.id in labeled_clip_ids]

        return jsonify([c.to_dict() for c in clips])


@bp.get("/<int:clip_id>")
def get_clip(clip_id: int):
    with session_scope() as session:
        clip = session.get(AudioClip, clip_id)
        if clip is None:
            abort(404)
        return jsonify(clip.to_dict())


@bp.get("/<int:clip_id>/audio")
def serve_clip_audio(clip_id: int):
    with session_scope() as session:
        clip = session.get(AudioClip, clip_id)
        if clip is None:
            abort(404)
        filename = clip.storage_filename
    return send_from_directory(_upload_dir(), filename)


@bp.post("")
def upload_clip():
    if "audio" not in request.files:
        return jsonify({"error": "No file"}), 400

    file = request.files["audio"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400

    safe_original = secure_filename(file.filename)
    if not safe_original:
        return jsonify({"error": "Invalid filename"}), 400

    ext = Path(safe_original).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext or '(none)'}"}), 400
    if file.mimetype and not file.mimetype.startswith("audio/"):
        return jsonify({"error": f"Unexpected MIME type: {file.mimetype}"}), 400

    tmp_name = f".tmp-{uuid.uuid4().hex}{ext}"
    tmp_path = _upload_dir() / tmp_name
    file.save(tmp_path)
    try:
        digest = _sha256_file(tmp_path)
        with session_scope() as session:
            user = get_or_create_current_user(session)
            existing = session.scalar(
                select(AudioClip).where(AudioClip.content_sha256 == digest)
            )
            if existing is not None:
                tmp_path.unlink(missing_ok=True)
                return jsonify({**existing.to_dict(), "duplicate": True}), 200

            final_name = f"{digest}{ext}"
            final_path = _upload_dir() / final_name
            os.replace(tmp_path, final_path)

            duration, sr = _probe_audio(final_path)

            clip = AudioClip(
                storage_filename=final_name,
                original_filename=safe_original,
                content_sha256=digest,
                duration_seconds=duration,
                sample_rate_hz=sr,
                uploaded_by=user.id,
            )
            session.add(clip)
            session.flush()
            return jsonify(clip.to_dict()), 201
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
