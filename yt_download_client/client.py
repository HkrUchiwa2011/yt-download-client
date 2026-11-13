import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx

from .exceptions import (
    AuthenticationError,
    JobFailedError,
    JobNotFoundError,
    JobTimeoutError,
    RateLimitError,
    ServerBusyError,
    YTDownloadError,
)
from .models import Job, VideoInfo

DEFAULT_POLL_INTERVAL = 5
DEFAULT_TIMEOUT = 600
VALID_STATUSES = {"pending", "started", "progress", "post_processing", "success", "failure"}


def _job_path(job_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
        raise ValueError("Invalid job identifier")
    return job_id


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "5")
    try:
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = 5
    return min(300, max(0, seconds))


def _safe_filename(disposition: str) -> str:
    message = Message()
    message["Content-Disposition"] = disposition
    filename = message.get_filename() or "download"
    if (
        len(filename) > 200
        or filename.startswith(".")
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
        or any(char in filename for char in '/\\:<>"|?*')
        or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", filename, re.I) is not None
        or filename.endswith((" ", "."))
    ):
        raise YTDownloadError("Server returned an unsafe filename")
    return filename


class YTDownloadClient:
    """Synchronous client. Use a context manager or close() to release connections.

    GET requests retry transient failures; submission is never automatically retried.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30,
        *,
        max_retries: int = 2,
        max_download_bytes: int = 1024**3,
    ):
        try:
            parts = urlsplit(base_url)
            valid = (
                parts.scheme in {"https", "http"}
                and parts.hostname
                and not parts.username
                and not parts.password
                and not parts.query
                and not parts.fragment
            )
            _ = parts.port
        except ValueError:
            valid = False
        if not valid or any(ord(char) <= 32 for char in base_url) or "\\" in base_url:
            raise ValueError(
                "base_url must be an HTTP(S) URL without credentials, query or fragment"
            )
        if not api_key or any(ord(char) < 32 or ord(char) == 127 for char in api_key):
            raise ValueError("api_key must be a nonempty HTTP header value")
        if (
            not math.isfinite(timeout)
            or timeout <= 0
            or not 0 <= max_retries <= 5
            or max_download_bytes <= 0
        ):
            raise ValueError("Invalid timeout, retry count or download size limit")
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_download_bytes = max_download_bytes
        self._client = httpx.Client(
            headers={"X-API-Key": api_key, "Accept-Encoding": "identity"},
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _check_response(self, response):
        if response.status_code == 401:
            raise AuthenticationError("Invalid or missing API key")
        if response.status_code == 404:
            raise JobNotFoundError("Job or file not found or expired")
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded", retry_after=_retry_after(response))
        if response.status_code == 503:
            raise ServerBusyError(
                "Server temporarily unavailable", retry_after=_retry_after(response)
            )
        if not response.is_success:
            # Do not echo untrusted response bodies or signed URLs/credentials.
            raise YTDownloadError(f"API returned HTTP {response.status_code}")
        if response.headers.get("Content-Encoding", "identity").strip().lower() not in {
            "",
            "identity",
        }:
            # Reject compression before decoding can allocate past the size limit.
            raise YTDownloadError("Encoded API responses are not supported")

    def _pause(self, delay, deadline):
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or delay >= remaining:
                raise JobTimeoutError("Job wait deadline reached")
        time.sleep(delay)

    def _request(self, method: str, path: str, *, _deadline=None, **kwargs) -> dict:
        retries = self._max_retries if method == "GET" else 0
        for attempt in range(retries + 1):
            remaining = (
                self._timeout
                if _deadline is None
                else min(self._timeout, _deadline - time.monotonic())
            )
            if remaining <= 0:
                raise JobTimeoutError("Job wait deadline reached")
            delay = None
            try:
                with self._client.stream(
                    method, f"{self._base}{path}", timeout=remaining, **kwargs
                ) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt < retries:
                        delay = (
                            _retry_after(response)
                            if response.status_code in {429, 503}
                            else 2**attempt
                        )
                    else:
                        self._check_response(response)
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body.extend(chunk)
                            if len(body) > 1024**2:
                                raise YTDownloadError("API response exceeds the size limit")
                            if _deadline is not None and time.monotonic() >= _deadline:
                                raise JobTimeoutError("Job wait deadline reached")
                        try:
                            data = json.loads(body)
                            if not isinstance(data, dict):
                                raise ValueError
                        except (ValueError, UnicodeError) as exc:
                            raise YTDownloadError("API returned an invalid JSON object") from exc
                        return data
            except httpx.RequestError as exc:
                if attempt == retries:
                    raise YTDownloadError("HTTP request failed") from exc
                delay = 2**attempt
            if delay is not None:
                self._pause(delay, _deadline)
        raise YTDownloadError("Request retry limit reached")

    @staticmethod
    def _job(data):
        try:
            identifier, status = data["job_id"], data["status"]
            _job_path(identifier)
            if status not in VALID_STATUSES:
                raise ValueError
            return Job(
                id=identifier,
                status=status,
                progress=data.get("progress"),
                download_url=data.get("download_url"),
                error=data.get("error"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise YTDownloadError("API returned an invalid job") from exc

    def health(self) -> dict:
        return self._request("GET", "/health")

    def info(self, url: str) -> VideoInfo:
        data = self._request("GET", "/info", params={"url": url})
        try:
            return VideoInfo(
                title=data["title"],
                duration=data["duration"],
                uploader=data.get("uploader"),
                thumbnail=data.get("thumbnail"),
                formats=data.get("formats", []),
                filesize_approx=data.get("filesize_approx"),
            )
        except (KeyError, TypeError) as exc:
            raise YTDownloadError("API returned invalid video metadata") from exc

    def submit(
        self, url: str, format: str = "mp4", quality: str = "best", webhook_url: str | None = None
    ) -> Job:
        payload = {"url": url, "format": format, "quality": quality}
        if webhook_url:
            payload["webhook_url"] = webhook_url
        return self._job(self._request("POST", "/download", json=payload))

    def status(self, job_id: str) -> Job:
        return self._job(self._request("GET", f"/status/{_job_path(job_id)}"))

    def wait(
        self,
        job_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        on_progress: Callable[[Job], None] | None = None,
    ) -> Job:
        _job_path(job_id)
        if (
            not math.isfinite(poll_interval)
            or poll_interval < 0
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("poll_interval and timeout must be finite and nonnegative")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self._job(self._request("GET", f"/status/{job_id}", _deadline=deadline))
            if on_progress:
                on_progress(job)
            if time.monotonic() >= deadline:
                break
            if job.status == "failure":
                raise JobFailedError(job.error or "Job failed")
            if job.status == "success":
                return job
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(poll_interval, remaining))
        raise JobTimeoutError(f"Job {job_id} did not finish within {timeout}s")

    def fetch(self, job_id: str, output: str | Path | None = None) -> Path:
        path = f"/file/{_job_path(job_id)}"
        for attempt in range(self._max_retries + 1):
            temporary = None
            try:
                with self._client.stream(
                    "GET", f"{self._base}{path}", headers={"Accept-Encoding": "identity"}
                ) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt < self._max_retries:
                        delay = (
                            _retry_after(response)
                            if response.status_code in {429, 503}
                            else 2**attempt
                        )
                    else:
                        self._check_response(response)
                        target = (
                            Path(output)
                            if output is not None
                            else Path(
                                _safe_filename(response.headers.get("Content-Disposition", ""))
                            )
                        )
                        expected = response.headers.get("Content-Length")
                        try:
                            expected = int(expected) if expected is not None else None
                        except ValueError as exc:
                            raise YTDownloadError("Invalid file size header") from exc
                        if expected is not None and not 0 <= expected <= self._max_download_bytes:
                            raise YTDownloadError("Download exceeds the configured size limit")
                        fd, name = tempfile.mkstemp(prefix=".yt-download-", dir=target.parent)
                        temporary = Path(name)
                        received = 0
                        with os.fdopen(fd, "wb") as file:
                            for chunk in response.iter_bytes():
                                received += len(chunk)
                                if received > self._max_download_bytes:
                                    raise YTDownloadError(
                                        "Download exceeds the configured size limit"
                                    )
                                file.write(chunk)
                            file.flush()
                            os.fsync(file.fileno())
                        if expected is not None and received != expected:
                            raise YTDownloadError("Incomplete download")
                        if output is None:
                            # Atomic no-clobber creation protects existing files and symlinks.
                            os.link(temporary, target)
                            temporary.unlink()
                        else:
                            os.replace(temporary, target)
                        temporary = None
                        return target
                self._pause(delay, None)
            except httpx.RequestError as exc:
                if attempt == self._max_retries:
                    raise YTDownloadError("File transfer failed") from exc
                self._pause(2**attempt, None)
            except OSError as exc:
                raise YTDownloadError(
                    "Cannot save download; destination may already exist"
                ) from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        raise YTDownloadError("File transfer retry limit reached")

    def download(
        self,
        url: str,
        format: str = "mp4",
        quality: str = "best",
        output: str | Path | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        on_progress: Callable[[Job], None] | None = None,
    ) -> Path:
        job = self.submit(url, format=format, quality=quality)
        self.wait(job.id, poll_interval=poll_interval, timeout=timeout, on_progress=on_progress)
        return self.fetch(job.id, output=output)

    def delete(self, job_id: str) -> dict:
        return self._request("DELETE", f"/file/{_job_path(job_id)}")
