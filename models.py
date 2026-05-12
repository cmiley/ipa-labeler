from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    authelia_sub: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    uploads: Mapped[list["AudioClip"]] = relationship(back_populates="uploader")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="user")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sub": self.authelia_sub,
            "email": self.email,
            "displayName": self.display_name,
            "isAdmin": self.is_admin,
        }


class AudioClip(Base):
    __tablename__ = "audio_clips"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    storage_filename: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="approved")

    uploader: Mapped[User | None] = relationship(back_populates="uploads")
    annotations: Mapped[list["Annotation"]] = relationship(
        back_populates="clip", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "originalFilename": self.original_filename,
            "durationSeconds": self.duration_seconds,
            "sampleRateHz": self.sample_rate_hz,
            "uploadedBy": self.uploaded_by,
            "uploadedAt": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "status": self.status,
        }


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("clip_id", "user_id", name="uq_annotation_clip_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    clip_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("audio_clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    clip: Mapped[AudioClip] = relationship(back_populates="annotations")
    user: Mapped[User] = relationship(back_populates="annotations")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "clipId": self.clip_id,
            "userId": self.user_id,
            "userDisplayName": self.user.display_name if self.user else None,
            "segments": self.segments,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
