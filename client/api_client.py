"""
Thin HTTP wrapper around the FastAPI backend defined in API_CONTRACT.md.

Deliberately dumb: one method call = one HTTP request. No hidden retries,
no backoff, no queuing. Retry policy belongs to transfer_queue.py per the
ownership doc ("Track pending uploads/downloads, failed transfers,
retryable operations") -- baking retries in here would blur that
boundary and make it harder for sync_runner to reason about what
actually failed versus what silently retried behind its back.

Upload's "conflict" outcome is a normal, documented response shape (see
API_CONTRACT.md's "Conflict response"), not an error -- upload_file()
returns a typed UploadResult covering both outcomes. Genuine failures
(can't reach the server, 5xx, a response body that doesn't match the
contract) raise ApiClientError subclasses instead, so callers can tell
"the server said no" apart from "we couldn't talk to the server."
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from models import RemoteFileState

logger = logging.getLogger(__name__)


class ApiClientError(Exception):
    """Base class for anything that goes wrong talking to the server."""


class ApiConnectionError(ApiClientError):
    """Couldn't reach the server at all (DNS, refused connection, timeout)."""


class ApiResponseError(ApiClientError):
    """Server responded, but not usefully -- unexpected status code or a
    body that doesn't match the shape API_CONTRACT.md promises."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class UploadResult:
    status: str  # "uploaded" or "conflict", straight from the response body
    relative_path: str
    version_id: str | None = None
    file_hash: str | None = None
    server_version_id: str | None = None  # populated on conflict
    reason: str | None = None             # populated on conflict

    @property
    def is_conflict(self) -> bool:
        return self.status == "conflict"


@dataclass
class DeleteResult:
    status: str
    relative_path: str
    version_id: str | None = None


def _parse_iso(timestamp: str) -> datetime:
    """API_CONTRACT.md's example timestamps use a trailing 'Z' (UTC).
    Handle it explicitly rather than depending on fromisoformat's
    Python-version-dependent 'Z' support."""
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp)


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        # transport is exposed for testing (httpx.MockTransport) -- real
        # usage never needs to pass it, httpx picks the real one.
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise ApiConnectionError(f"Could not reach server for {method} {url}: {exc}") from exc

        if response.status_code >= 500:
            raise ApiResponseError(
                f"Server error on {method} {url}: {response.status_code}",
                status_code=response.status_code,
            )

        return response

    def _json(self, response: httpx.Response) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            raise ApiResponseError(
                f"Response body wasn't valid JSON (status {response.status_code})",
                status_code=response.status_code,
            ) from exc

    # -- Health ----------------------------------------------------------

    def health(self) -> bool:
        response = self._request("GET", "/health")
        return response.status_code == 200 and self._json(response).get("status") == "ok"

    # -- Devices / sync spaces --------------------------------------------
    # API_CONTRACT.md gives a request/response example for POST /devices
    # and POST /sync-spaces, but doesn't show an example body for the
    # GET (list) variants of either -- so those two return the raw
    # parsed response rather than guessing a key name that might not
    # match Person 1's actual backend. Worth asking for a concrete
    # example to be added to the contract.

    def register_device(self, name: str) -> str:
        response = self._request("POST", "/devices", json={"name": name})
        if response.status_code >= 400:
            raise ApiResponseError(f"Device registration failed: {response.status_code}", response.status_code)
        return self._json(response)["device_id"]

    def list_devices(self) -> dict:
        response = self._request("GET", "/devices")
        if response.status_code >= 400:
            raise ApiResponseError(f"Listing devices failed: {response.status_code}", response.status_code)
        return self._json(response)

    def create_sync_space(self, name: str) -> str:
        response = self._request("POST", "/sync-spaces", json={"name": name})
        if response.status_code >= 400:
            raise ApiResponseError(f"Sync space creation failed: {response.status_code}", response.status_code)
        return self._json(response)["sync_space_id"]

    def list_sync_spaces(self) -> dict:
        response = self._request("GET", "/sync-spaces")
        if response.status_code >= 400:
            raise ApiResponseError(f"Listing sync spaces failed: {response.status_code}", response.status_code)
        return self._json(response)

    # -- File metadata / transfer -----------------------------------------

    def list_remote_files(self, sync_space_id: str) -> dict[str, RemoteFileState]:
        """Returns dict[relative_path, RemoteFileState] -- this is the
        exact shape sync_planner.plan_sync() expects as its remote_states
        argument, so callers can pass this straight through."""
        response = self._request("GET", f"/sync-spaces/{sync_space_id}/files")
        if response.status_code >= 400:
            raise ApiResponseError(
                f"Listing remote files failed: {response.status_code}", response.status_code
            )

        body = self._json(response)
        result: dict[str, RemoteFileState] = {}
        for entry in body.get("files", []):
            state = RemoteFileState(
                relative_path=entry["relative_path"],
                version_id=entry["version_id"],
                file_hash=entry["file_hash"],
                size_bytes=entry["size_bytes"],
                deleted=entry["deleted"],
                updated_at=_parse_iso(entry["updated_at"]),
            )
            result[state.relative_path] = state
        return result

    def upload_file(
        self,
        sync_space_id: str,
        device_id: str,
        relative_path: str,
        file_hash: str,
        size_bytes: int,
        modified_time: float,
        base_version_id: str | None,
        local_path: Path,
    ) -> UploadResult:
        form_data = {
            "device_id": device_id,
            "relative_path": relative_path,
            "file_hash": file_hash,
            "size_bytes": str(size_bytes),
            "modified_time": str(modified_time),
        }
        # Omit rather than send an empty string for "no known base" --
        # API_CONTRACT.md marks base_version_id nullable, and an absent
        # form field is the more honest way to say "I don't have one"
        # than sending base_version_id="".
        if base_version_id is not None:
            form_data["base_version_id"] = base_version_id

        with open(local_path, "rb") as f:
            response = self._request(
                "POST",
                f"/sync-spaces/{sync_space_id}/files/upload",
                data=form_data,
                files={"file": (Path(local_path).name, f)},
            )

        body = self._json(response)
        status = body.get("status")

        # API_CONTRACT.md doesn't specify what HTTP status code the
        # conflict response uses, so trust the body's "status" field as
        # ground truth rather than assuming a status-code convention
        # (200 vs 409) the contract never actually commits to.
        if status not in ("uploaded", "conflict"):
            raise ApiResponseError(
                f"Unexpected upload response for {relative_path}: "
                f"HTTP {response.status_code}, body={body}",
                status_code=response.status_code,
            )

        return UploadResult(
            status=status,
            relative_path=body.get("relative_path", relative_path),
            version_id=body.get("version_id"),
            file_hash=body.get("file_hash"),
            server_version_id=body.get("server_version_id"),
            reason=body.get("reason"),
        )

    def download_file(
        self,
        sync_space_id: str,
        relative_path: str,
        destination: Path,
        version_id: str | None = None,
    ) -> None:
        """
        Streams the file straight to `destination`. Deliberately does NOT
        do the temp-file-then-atomic-rename dance or post-download hash
        verification that SYNC_PROTOCOL.md's Download Flow requires --
        that's filesystem policy, owned by sync_runner, not this
        transport layer. Callers should pass a temp path here and handle
        the atomic replace + hash check themselves.
        """
        params = {"relative_path": relative_path}
        if version_id is not None:
            params["version_id"] = version_id

        try:
            with self._client.stream(
                "GET", f"/sync-spaces/{sync_space_id}/files/download", params=params
            ) as response:
                if response.status_code >= 400:
                    raise ApiResponseError(
                        f"Download failed for {relative_path}: {response.status_code}",
                        status_code=response.status_code,
                    )
                with open(destination, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except httpx.RequestError as exc:
            raise ApiConnectionError(
                f"Could not reach server to download {relative_path}: {exc}"
            ) from exc

    def delete_file(
        self,
        sync_space_id: str,
        device_id: str,
        relative_path: str,
        base_version_id: str | None,
    ) -> DeleteResult:
        """
        NOTE: API_CONTRACT.md tags this endpoint [NEXT] (Phase 2), but
        SYNC_PROTOCOL.md's Phase-1 "Sync Decisions" table already
        includes tombstone upload as a Phase-1 behavior, and
        SyncAction.UPLOAD_TOMBSTONE already exists in models.py. Wrapped
        here since the contract documents a concrete request/response
        shape either way -- but confirm with Person 1 whether the
        backend route actually exists before sync_runner calls this for
        real.
        """
        payload = {"device_id": device_id, "relative_path": relative_path}
        if base_version_id is not None:
            payload["base_version_id"] = base_version_id

        response = self._request(
            "POST", f"/sync-spaces/{sync_space_id}/files/delete", json=payload
        )
        if response.status_code >= 400:
            raise ApiResponseError(
                f"Delete failed for {relative_path}: {response.status_code}", response.status_code
            )

        body = self._json(response)
        return DeleteResult(
            status=body["status"],
            relative_path=body.get("relative_path", relative_path),
            version_id=body.get("version_id"),
        )