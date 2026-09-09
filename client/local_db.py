"""
Client-side SQLite metadata store.

This module is a Repository: it knows how to read and write local sync
state as rows, and nothing about *when* those writes should happen or
what they mean for sync decisions -- that's change_detector.py and
sync_planner.py. Same policy/mechanism split already used for
sync_planner (pure decision function) vs sync_runner (orchestration).

All three client tables from DATABASE_SCHEMA.md are created up front so
transfer_queue.py and conflict_handler.py won't need their own migration
step later. Only local_files gets full CRUD here, though -- that's what
change_detector/sync_planner need for Phase 1. Repository methods for
pending_transfers/conflicts are deliberately left out until the modules
that actually use them exist; writing that API now would mean guessing
at shapes those modules haven't defined yet.

DEVIATION FROM DATABASE_SCHEMA.md, FLAGGED FOR THE TEAM DOC:
local_files.modified_time is documented as TEXT there, but
SyncRecord.modified_time (models.py) is already typed float, matching
ScanResult.modified_time straight out of os.stat().st_mtime. Re-typing
it to a string now would mean lossy/awkward float<->ISO round-tripping
for no real benefit, so this stores it as SQLite REAL instead. The other
two timestamp columns (last_scanned_at, last_synced_at) *are* genuine
ISO-8601 TEXT, matching the schema's general timestamp rule and
SyncRecord's datetime typing -- just modified_time is the odd one out.
Worth a one-line fix to DATABASE_SCHEMA.md so Person 1 sees it too.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from models import SyncRecord, SyncStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS local_files (
    relative_path     TEXT PRIMARY KEY,
    file_hash         TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL,
    modified_time     REAL NOT NULL,
    server_version_id TEXT,
    sync_status       TEXT NOT NULL,
    deleted           INTEGER NOT NULL DEFAULT 0,
    last_scanned_at   TEXT NOT NULL,
    last_synced_at    TEXT
);

CREATE TABLE IF NOT EXISTS pending_transfers (
    id            TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL,
    direction     TEXT NOT NULL,
    status        TEXT NOT NULL,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conflicts (
    id                TEXT PRIMARY KEY,
    relative_path     TEXT NOT NULL,
    conflict_path     TEXT NOT NULL,
    local_hash        TEXT NOT NULL,
    server_version_id TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    resolved          INTEGER NOT NULL DEFAULT 0
);
"""


def _record_to_params(record: SyncRecord) -> tuple:
    return (
        record.relative_path,
        record.file_hash,
        record.size_bytes,
        record.modified_time,
        record.server_version_id,
        record.sync_status.value,  # raw "dirty"/"synced"/etc, NOT str(enum_member)
        int(record.deleted),
        record.last_scanned_at.isoformat(),
        record.last_synced_at.isoformat() if record.last_synced_at is not None else None,
    )


def _row_to_record(row: sqlite3.Row) -> SyncRecord:
    return SyncRecord(
        relative_path=row["relative_path"],
        file_hash=row["file_hash"],
        size_bytes=row["size_bytes"],
        modified_time=row["modified_time"],
        server_version_id=row["server_version_id"],
        sync_status=SyncStatus(row["sync_status"]),
        deleted=bool(row["deleted"]),
        last_scanned_at=datetime.fromisoformat(row["last_scanned_at"]),
        last_synced_at=(
            datetime.fromisoformat(row["last_synced_at"])
            if row["last_synced_at"] is not None
            else None
        ),
    )


class LocalDB:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_record(self, record: SyncRecord) -> None:
        """
        Insert or update the row for record.relative_path, keyed on the
        path (PRIMARY KEY). This is the ONLY write path for local_files
        -- there's no separate "mark as deleted" method, because a
        tombstone is just a SyncRecord with deleted=True and
        sync_status=SyncStatus.DELETED, upserted like anything else.
        One write path means one place that can get the transition
        logic wrong, and it keeps this an incremental ledger (per-path
        upsert) rather than a destructive wipe-and-rebuild.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO local_files (
                    relative_path, file_hash, size_bytes, modified_time,
                    server_version_id, sync_status, deleted,
                    last_scanned_at, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    file_hash         = excluded.file_hash,
                    size_bytes        = excluded.size_bytes,
                    modified_time     = excluded.modified_time,
                    server_version_id = excluded.server_version_id,
                    sync_status       = excluded.sync_status,
                    deleted           = excluded.deleted,
                    last_scanned_at   = excluded.last_scanned_at,
                    last_synced_at    = excluded.last_synced_at
                """,
                _record_to_params(record),
            )

    def get_record(self, relative_path: str) -> SyncRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM local_files WHERE relative_path = ?",
                (relative_path,),
            ).fetchone()

        return _row_to_record(row) if row is not None else None

    def get_all_records(self) -> dict[str, SyncRecord]:
        """
        Returns a dict keyed by relative_path rather than a list.
        change_detector's whole job is repeatedly asking "what does the
        DB say about this path from the current scan?" -- a dict makes
        that an O(1) lookup instead of forcing every caller to build
        the same index themselves.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM local_files").fetchall()

        return {row["relative_path"]: _row_to_record(row) for row in rows}

    def delete_record(self, relative_path: str) -> None:
        """
        Hard delete -- removes the row entirely. This is NOT how normal
        file deletions are represented (that's upsert_record with
        deleted=True, so the tombstone can still sync to other clients).
        This exists for test cleanup and for permanently forgetting a
        path once its tombstone has fully propagated -- a decision left
        for whichever later module actually needs to prune tombstones.
        """
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM local_files WHERE relative_path = ?",
                (relative_path,),
            )