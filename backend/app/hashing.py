"""
Hashing utilities for verifying uploaded file content.

Core principle (from API_CONTRACT.md): "The server must verify file
hash after upload." The client SENDS a claimed hash, it independently 
recomputes the hash from the actual bytes it received and compares the two.
"""

import hashlib
from pathlib import Path

# Read files in 1MB pieces rather than loading the whole thing into
# memory at once.
CHUNK_SIZE = 1024 * 1024 # 1 MB

def compute_file_hash(file_path: Path) -> str:
    """
    Computes the SHA-256 hash of a file already saved on disk.

    Instead of using plain string ("/home/meet/backend/storage/tmp/upload123.txt"), 
    Path gives you useful behavior — e.g. file_path.name gives you just the filename, 
    file_path.parent gives you the folder it's in, and  can do open(file_path, "rb") directly.

    Returns the hash as a lowercase hex string (64 characters) --
    e.g. "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".
    This gets stored in FileVersion.file_hash and compared against the client's claim.
    """
    hasher = hashlib.sha256()

    # "rb" = read in binary mode. Binary, not text, because we want 
    # the exact bytes, unchanged, whether it's a .txt file, a .jpg, or anything else.
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)

            # An empty chunk means we've reached the end of the file --
            # read() returns b"" (empty bytes) once there's nothing left.
            if not chunk:
                break

            # Feed this piece into the running hash calculation.
            # SHA-256 is designed so that hashing incrementally like
            # this produces the EXACT SAME final result as hashing the
            # whole file in one go -- we're not losing any accuracy by
            # doing it in pieces.
            hasher.update(chunk)

    return hasher.hexdigest()

def verify_file_hash(file_path: Path, claimed_hash: str) -> bool:
    """
    Checks whether a file's ACTUAL hash matches what the client CLAIMED
    it should be.

    .lower() on both sides: hashes are just hex text, and hex can
    technically be written in uppercase or lowercase (both "AB12" and
    "ab12" represent the same bytes).
    """
    actual_hash = compute_file_hash(file_path)
    return actual_hash.lower() == claimed_hash.lower()