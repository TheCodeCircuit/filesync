"""
Defines our DATABASE TABLES as Python classes.

Important distinction to keep straight (comes up constantly):
  - models.py  = the shape of data IN THE DATABASE (internal truth)
  - schemas.py = the shape of data going OVER THE NETWORK (what the
                 outside world sees in JSON)
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Device(Base):
    __tablename__ = "devices"

    # String(36) specifically fits a UUID's string length exactly
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    # NOTE: this gets set once at creation and
    # nothing currently updates it afterward. Its name implies it
    # should track the device's most recent activity -- worth revisiting
    # once we have an endpoint that would naturally touch it.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class SyncSpace(Base):
    __tablename__ = "sync_spaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # ForeignKey("sync_spaces.id") tells SQLAlchemy (and the database)
    # "this column's value must match an existing id in the
    # sync_spaces table.
    sync_space_id: Mapped[str] = mapped_column(String(36), ForeignKey("sync_spaces.id"), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Points at the currently-active row in file_versions.
    # `str | None` = this can be a string OR None (nullable).
    # It starts as None the instant a path is first known about.
    #
    # NOTE: deliberately NOT a real ForeignKey (problem at creating the database) 
    # -- this avoids a circular table dependency with file_versions. Our own service code
    # is responsible for keeping this accurate.
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # sqlite doesn't have boolean values, but sqlalchemy handles the 0s and 1s for us.
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # __table_args__ is where you put constraints that involve MORE
    # THAN ONE column at once (a single mapped_column can't express
    # "these two columns together must be unique").
    #
    # This says: the same sync_space_id can appear many times (many
    # files in one space), and the same relative_path can appear many
    # times (same filename in different spaces) -- but the COMBINATION
    # of the two must be unique.
    __table_args__ = (UniqueConstraint("sync_space_id", "relative_path", name="uq_file_space_path"), )

class FileVersion(Base):
    __tablename__ = "file_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False)

    # The version it THOUGHT was current
    # when the device made this upload.
    #
    # This is a SELF-referencing foreign key (file_versions pointing at
    # its own table) -- no cycle problem, because it's just one table
    # referencing itself, not two tables needing each other.
    base_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("file_versions.id"), nullable=True)

    # SHA-256 hashes are always exactly 64 hex characters
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # WHERE the actual file bytes live on disk (inside backend/storage/objects/).
    # This is a path relative to STORAGE_DIR, not the file's original relative_path.
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)