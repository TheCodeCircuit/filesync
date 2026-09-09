"""
Filesystem scanner: walks a sync folder and yields a ScanResult for every
regular, readable, non-excluded file underneath it.

Scanner is intentionally "dumb": it walks the filesystem and extracts raw
metadata only. It does not index by relative_path, does not compare
against local_db, and does not know about sync state -- that's
change_detector's job one module over. Keeping it a pure mechanism (no
policy) makes it trivially testable against a tmp directory and keeps the
same policy/mechanism split already used between sync_planner and
sync_runner.
"""

import logging
import os
from pathlib import Path, PurePosixPath

from models import ScanResult

logger = logging.getLogger(__name__)

# Relative-path prefix reserved for local sync metadata (per
# ARCHITECTURE.md: "stored outside the synced folder or in an ignored
# .filesync/ directory"). Never treated as syncable content, regardless
# of which storage location the running client actually uses.
SYNC_METADATA_DIR = ".filesync"


def _to_posix_relative_path(path: Path, root: Path) -> str:
    """Normalize to forward-slash relative paths regardless of OS.
    API_CONTRACT.md's relative_path examples use '/', and every later
    comparison against server metadata / local_db assumes it too."""
    return PurePosixPath(path.relative_to(root)).as_posix()


def _is_excluded(relative_path: str) -> bool:
    return relative_path == SYNC_METADATA_DIR or relative_path.startswith(
        f"{SYNC_METADATA_DIR}/"
    )


def _walk_no_symlink_dirs(root: Path):
    """os.walk wrapper that refuses to descend into symlinked directories.

    followlinks=False already stops os.walk from recursing into them, but
    it still lists them in dirnames -- prune explicitly so nothing
    downstream mistakes a symlinked dir for a real subdirectory, and so a
    symlink cycle (dir pointing back at an ancestor) can't cause runaway
    or duplicate scanning.
    """
    for dirpath_str, dirnames, filenames in os.walk(root, followlinks=False):
        dirpath = Path(dirpath_str)
        dirnames[:] = [d for d in dirnames if not (dirpath / d).is_symlink()]
        yield dirpath, dirnames, filenames


def iter_files(root: Path):
    """Yield every regular file under root: no symlinks (files or dirs),
    no special files (sockets/devices/etc), lazily."""
    for dirpath, _dirnames, filenames in _walk_no_symlink_dirs(root):
        for name in filenames:
            candidate = dirpath / name

            if candidate.is_symlink():
                continue
            if not candidate.is_file():
                continue

            yield candidate


def extract_metadata(path: Path, relative_path: str) -> ScanResult | None:
    """
    Build a ScanResult for one file.

    Returns None (and logs a warning) if metadata can't be safely read --
    most commonly because the file was deleted between listing and stat,
    a real race once watcher.py is triggering scans off live filesystem
    events, or because of a permissions error. Either way this scan
    simply won't include the file, which change_detector.py is
    responsible for interpreting correctly (a file missing from a scan
    isn't automatically "deleted" -- that's a design question left for
    change_detector, not decided here).
    """
    try:
        stat = path.stat()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        logger.warning("Skipping unreadable file %s: %s", path, exc)
        return None

    return ScanResult(
        relative_path=relative_path,
        size_bytes=stat.st_size,
        modified_time=stat.st_mtime,
        inode=stat.st_ino,
    )


def scan_dir(root: str | Path):
    """
    Lazily scan `root`, yielding a ScanResult per eligible file.

    Accepts str or Path so callers can pass UserConfig.sync_folder
    straight in without wrapping it first -- config.py owns sync_folder
    as str, scanner shouldn't force every caller to know that.
    """
    root = Path(root)

    for path in iter_files(root):
        relative_path = _to_posix_relative_path(path, root)

        if _is_excluded(relative_path):
            continue

        metadata = extract_metadata(path, relative_path)
        if metadata is not None:
            yield metadata
