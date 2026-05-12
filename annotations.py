from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import select

from auth import get_or_create_current_user
from db import session_scope
from models import Annotation, AudioClip

bp = Blueprint("annotations", __name__, url_prefix="/api/clips")


def _validate_segments(payload) -> list[dict]:
    if not isinstance(payload, list):
        abort(400, description="segments must be a JSON array")
    cleaned = []
    for s in payload:
        if not isinstance(s, dict):
            abort(400, description="each segment must be an object")
        start_raw = s.get("startTime")
        end_raw = s.get("endTime")
        if not isinstance(start_raw, (int, float)) or not isinstance(end_raw, (int, float)):
            abort(400, description="each segment needs numeric startTime and endTime")
        start = float(start_raw)
        end = float(end_raw)
        if end <= start:
            abort(400, description=f"segment endTime ({end}) must exceed startTime ({start})")
        cleaned.append(
            {
                "startTime": start,
                "endTime": end,
                "text": str(s.get("text", "")),
                "semanticLabel": str(s.get("semanticLabel", "")),
            }
        )
    return cleaned


@bp.get("/<int:clip_id>/annotations")
def get_annotations(clip_id: int):
    """user=me (default) returns current user's annotation; user=all returns all."""
    scope = request.args.get("user", "me")

    with session_scope() as session:
        clip = session.get(AudioClip, clip_id)
        if clip is None:
            abort(404)

        user = get_or_create_current_user(session)
        if scope == "me":
            ann = session.scalar(
                select(Annotation).where(
                    Annotation.clip_id == clip_id, Annotation.user_id == user.id
                )
            )
            return jsonify(ann.to_dict() if ann else None)

        anns = session.scalars(
            select(Annotation).where(Annotation.clip_id == clip_id).order_by(Annotation.user_id)
        ).all()
        return jsonify([a.to_dict() for a in anns])


@bp.put("/<int:clip_id>/annotations")
def upsert_annotation(clip_id: int):
    segments = _validate_segments(request.get_json(silent=True))

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
        if ann is None:
            ann = Annotation(clip_id=clip_id, user_id=user.id, segments=segments)
            session.add(ann)
        else:
            ann.segments = segments
        session.flush()
        return jsonify(ann.to_dict())


@bp.delete("/<int:clip_id>/annotations")
def delete_annotation(clip_id: int):
    with session_scope() as session:
        user = get_or_create_current_user(session)
        ann = session.scalar(
            select(Annotation).where(
                Annotation.clip_id == clip_id, Annotation.user_id == user.id
            )
        )
        if ann is None:
            return jsonify({"deleted": False}), 404
        session.delete(ann)
        return jsonify({"deleted": True})
