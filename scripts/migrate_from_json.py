"""One-shot migration from Phase-1 annotations.json to Phase-2 Postgres.

Reads annotations.json keyed by filename. For each filename:
  1. Locates the audio file in UPLOAD_FOLDER, computes sha256.
  2. Inserts (or finds) an audio_clips row.
  3. Inserts an annotations row owned by a synthetic 'legacy-system' user
     containing the segments from the JSON.

Idempotent: re-running with the same JSON updates the same annotation row.

Run inside the cluster pod after Phase 2 deploys but before users log in:
    kubectl -n ipa-labeler exec -it deploy/ipa-labeler -- \
        uv run python scripts/migrate_from_json.py

Or locally for testing against the dev DB:
    DATABASE_URL=postgresql://ipa:ipa@127.0.0.1:5432/ipa_labeler \
        IPA_LABELER_DATA_DIR=. \
        uv run python scripts/migrate_from_json.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# Allow running as a top-level script: scripts/ → parent dir on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402

from db import session_scope  # noqa: E402
from models import Annotation, AudioClip, User  # noqa: E402

LEGACY_SUB = "legacy-system"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    data_dir = Path(os.environ.get("IPA_LABELER_DATA_DIR", ".")).resolve()
    annotations_path = data_dir / "annotations.json"
    uploads = data_dir / "uploads"

    if not annotations_path.exists():
        print(f"[migrate] no annotations.json at {annotations_path}; nothing to do")
        return 0

    payload = json.loads(annotations_path.read_text())
    if not isinstance(payload, dict):
        print(f"[migrate] unexpected annotations.json shape ({type(payload).__name__}); aborting")
        return 1

    migrated = 0
    skipped = 0
    with session_scope() as session:
        system_user = session.scalar(select(User).where(User.authelia_sub == LEGACY_SUB))
        if system_user is None:
            system_user = User(
                authelia_sub=LEGACY_SUB,
                email=None,
                display_name="legacy (pre-Postgres)",
                is_admin=False,
            )
            session.add(system_user)
            session.flush()

        for filename, segments in payload.items():
            if not segments:
                skipped += 1
                continue
            audio_path = uploads / filename
            if not audio_path.exists():
                print(f"[migrate] skip '{filename}': file missing from {uploads}")
                skipped += 1
                continue

            digest = _sha256(audio_path)
            clip = session.scalar(select(AudioClip).where(AudioClip.content_sha256 == digest))
            if clip is None:
                clip = AudioClip(
                    storage_filename=filename,
                    original_filename=filename,
                    content_sha256=digest,
                    uploaded_by=None,
                    status="approved",
                )
                session.add(clip)
                session.flush()

            existing = session.scalar(
                select(Annotation).where(
                    Annotation.clip_id == clip.id, Annotation.user_id == system_user.id
                )
            )
            if existing is None:
                session.add(
                    Annotation(clip_id=clip.id, user_id=system_user.id, segments=segments)
                )
            else:
                existing.segments = segments
            migrated += 1
            print(f"[migrate] '{filename}' → clip id={clip.id} ({len(segments)} segments)")

    print(f"[migrate] done. migrated={migrated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
