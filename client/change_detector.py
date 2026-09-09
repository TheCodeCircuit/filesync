"""
Change detection: diffs "what's on disk right now" against "what local_db
last knew" and classifies each path as added/modified/deleted/unchanged.

This is a pure function, deliberately -- same reasoning as sync_planner
being a pure decision function with zero I/O. change_detector does not
touch the filesystem (scanner/hasher already did that) and does not
touch SQLite (local_db already did that). It just takes two already-
materialized views of the world and diffs them. That makes it directly
unit-testable with hand-built LocalFileState/SyncRecord fixtures, no
tmp directories or real DB required.

Composition with the modules already built:

    states = hasher.build_local_file_states(scanner.scan_dir(root), root)
    previous = local_db_instance.get_all_records()
    changes = detect_changes(states, previous)
"""

from models import Change, ChangeSet, ChangeType, LocalFileState, SyncRecord


def detect_changes(
    current_states,
    previous_records: dict[str, SyncRecord],
) -> ChangeSet:
    """
    current_states: iterable of LocalFileState from this scan pass (any
    iterable is fine -- it's fully consumed into a dict here, since
    deletion detection requires knowing the complete current set before
    it can tell what's missing from it).

    previous_records: dict[relative_path, SyncRecord] from
    LocalDB.get_all_records() -- last known state per path.

    Classification rules:
      - Path in current scan, no previous record, OR previous record
        exists but was itself a tombstone (deleted=True) -> ADDED.
        A previously-deleted path reappearing is treated as new, not
        "modified", since there's no meaningful prior version to diff
        against from the sync engine's point of view.
      - Path in current scan, previous record exists and isn't a
        tombstone, hash differs -> MODIFIED.
      - Path in current scan, previous record exists and isn't a
        tombstone, hash matches -> UNCHANGED.
      - Path in previous records (and not already a tombstone), missing
        from current scan -> DELETED. Paths that were already tombstoned
        and are still absent aren't re-reported -- there's nothing new
        to say about them.
    """
    current_by_path: dict[str, LocalFileState] = {
        state.relative_path: state for state in current_states
    }

    added: list[Change] = []
    modified: list[Change] = []
    unchanged: list[Change] = []
    deleted: list[Change] = []

    for relative_path, state in current_by_path.items():
        old_record = previous_records.get(relative_path)

        if old_record is None or old_record.deleted:
            added.append(
                Change(relative_path, ChangeType.ADDED, old_record, state)
            )
        elif state.file_hash != old_record.file_hash:
            modified.append(
                Change(relative_path, ChangeType.MODIFIED, old_record, state)
            )
        else:
            unchanged.append(
                Change(relative_path, ChangeType.UNCHANGED, old_record, state)
            )

    for relative_path, old_record in previous_records.items():
        if old_record.deleted:
            continue
        if relative_path not in current_by_path:
            deleted.append(
                Change(relative_path, ChangeType.DELETED, old_record, None)
            )

    return ChangeSet(added=added, deleted=deleted, modified=modified, unchanged=unchanged)
