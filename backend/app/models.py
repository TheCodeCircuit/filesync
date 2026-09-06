"""
Defines our DATABASE TABLES as Python classes.

Important distinction to keep straight (comes up constantly):
  - models.py  = the shape of data IN THE DATABASE (internal truth)
  - schemas.py = the shape of data going OVER THE NETWORK (what the
                 outside world sees in JSON)
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
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
