from __future__ import annotations

import os

from flask import abort, request
from sqlalchemy.orm import Session

from models import User

# In development the Authelia headers aren't present; allow a fallback sub for
# local iteration when IPA_LABELER_DEV_USER is set. Production never sets this.
_DEV_USER = os.environ.get("IPA_LABELER_DEV_USER")


def _header_user() -> tuple[str, str | None, str | None]:
    sub = request.headers.get("Remote-User")
    if not sub and _DEV_USER:
        return _DEV_USER, f"{_DEV_USER}@dev.local", _DEV_USER
    if not sub:
        abort(401, description="Missing Remote-User header (Authelia not in front?)")
    return sub, request.headers.get("Remote-Email"), request.headers.get("Remote-Name")


def get_or_create_current_user(session: Session) -> User:
    sub, email, display_name = _header_user()
    user = session.query(User).filter_by(authelia_sub=sub).one_or_none()
    if user is None:
        user = User(authelia_sub=sub, email=email, display_name=display_name or sub)
        session.add(user)
        session.flush()
    else:
        # Refresh display info if Authelia gives us better data than we have
        if email and not user.email:
            user.email = email
        if display_name and not user.display_name:
            user.display_name = display_name
    return user
