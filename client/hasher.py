"""
Content hashing for the local sync engine.

Two responsibilities, kept separate on purpose:
  1. hash_file / hash_bytes -- pure hashing primitives, no knowledge of
     scanning or sync state. hash_bytes exists now (even though nothing
     calls it yet) because chunker.py will eventually need to hash
     individual chunks with the exact same algorithm, and it should reuse
     this rather than reimplementing hashing later.
  2. build_local_file_state[s] -- the glue that turns scanner.py's output
     (ScanResult) into what change_detector/sync_planner actually
     consume (LocalFileState), by attaching a content hash.

NOTE ON "chunk size": DEFAULT_CHUNK_SIZE below is a *read-buffer* size --
how much of a file is pulled into memory per read() call while streaming
it through the hasher. It has nothing to do with the fixed-size sync
chunks chunker.py will define later for delta transfer/dedup (those are
a protocol-level concept and will likely be a different, larger size).
Don't let the two "chunk"s collide when chunker.py gets built.
"""

import hashlib
import logging
from pathlib import Path

from models import LocalFileState, ScanResult

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB read buffer, not a sync chunk


def hash_bytes(data: bytes) -> str:
    """SHA-256 hex digest of an in-memory blob. Reused later by
    chunker.py for per-chunk hashes -- same algorithm, same format."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str | None:
    """
    Stream `path` through SHA-256 in fixed-size reads rather than loading
    the whole file into memory -- required for large files per the
    project's ownership doc.

    Returns None (and logs) if the file can't be read -- most commonly
    because it was deleted or permissions changed between scan and hash,
    the same race scanner.py already tolerates for stat(). A None here
    means "this file didn't make it into this sync pass," not
    necessarily "this file was deleted" -- that interpretation belongs to
    change_detector, not here.
    """
    hasher = hashlib.sha256()

    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(chunk_size)
                if not block:
                    break
                hasher.update(block)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        logger.warning("Skipping unhashable file %s: %s", path, exc)
        return None

    return hasher.hexdigest()


def build_local_file_state(scan_result: ScanResult, root: Path) -> LocalFileState | None:
    """
    Combine one ScanResult with its content hash to produce the
    LocalFileState the rest of the pipeline operates on.

    root is needed because ScanResult only carries the *relative* path
    (by design, so it's directly comparable to server/local_db paths) --
    hashing needs the real filesystem location.
    """
    absolute_path = Path(root) / scan_result.relative_path
    file_hash = hash_file(absolute_path)

    if file_hash is None:
        return None

    return LocalFileState(scan=scan_result, file_hash=file_hash)


def build_local_file_states(scan_results, root: Path):
    """
    Lazily turn an iterable of ScanResult (e.g. scanner.scan_dir(root))
    into LocalFileState objects, silently dropping any file that became
    unreadable in the gap between scanning and hashing.

    Kept as a thin generator, not a batch/list function, so it composes
    directly with scan_dir without forcing either step to fully
    materialize first:

        states = hasher.build_local_file_states(scanner.scan_dir(root), root)
    """
    for scan_result in scan_results:
        state = build_local_file_state(scan_result, root)
        if state is not None:
            yield state