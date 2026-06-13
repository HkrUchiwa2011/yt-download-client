import time
import httpx
from pathlib import Path
from typing import Callable

from .models import Job, VideoInfo
from .exceptions import (
    AuthenticationError,
    RateLimitError,
    JobFailedError,
    JobNotFoundError,
    JobTimeoutError,
    ServerBusyError,
    YTDownloadError,
)

DEFAULT_POLL_INTERVAL = 5
DEFAULT_TIMEOUT = 600


class YTDownloadClient:
    """
    Client for the yt-download-api.

    Usage:
        client = YTDownloadClient(base_url="https://your-api.com", api_key="YOUR_KEY")
        client.download("https://youtu.be/...")
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self._base = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key}
        self._timeout = timeout

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base}{path}"
        try:
            r = httpx.request(
                method, url,
                headers=self._headers,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.RequestError as e:
            raise YTDownloadError(f"Request failed: {e}") from e

        if r.status_code == 401:
            raise AuthenticationError("Invalid API key")
        if r.status_code == 404:
            raise JobNotFoundError("Job not found or expired")
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "60")
            raise RateLimitError(f"Rate limit exceeded. Retry after {retry_after}s")
        if r.status_code == 503:
            raise ServerBusyError("Server is busy. Try again later.")
        if not r.is_success:
            raise YTDownloadError(f"API error {r.status_code}: {r.text}")

        return r.json()

    def health(self) -> dict:
        """Check API health and active download count."""
        return self._request("GET", "/health")

    def info(self, url: str) -> VideoInfo:
        """Fetch video metadata and available formats without downloading."""
        data = self._request("GET", "/info", params={"url": url})
        return VideoInfo(
            title=data["title"],
            duration=data["duration"],
            uploader=data.get("uploader"),
            thumbnail=data.get("thumbnail"),
            formats=data.get("formats", []),
            filesize_approx=data.get("filesize_approx"),
        )

    def submit(
        self,
        url: str,
        format: str = "mp4",
        quality: str = "best",
        webhook_url: str | None = None,
    ) -> Job:
        """Submit a download job and return immediately with a Job object."""
        payload = {"url": url, "format": format, "quality": quality}
        if webhook_url:
            payload["webhook_url"] = webhook_url

        data = self._request("POST", "/download", json=payload)
        return Job(id=data["job_id"], status=data["status"])

    def status(self, job_id: str) -> Job:
        """Fetch the current status of a job."""
        data = self._request("GET", f"/status/{job_id}")
        return Job(
            id=data["job_id"],
            status=data["status"],
            progress=data.get("progress"),
            download_url=data.get("download_url"),
            error=data.get("error"),
        )

    def wait(
        self,
        job_id: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        timeout: int = DEFAULT_TIMEOUT,
        on_progress: Callable[[Job], None] | None = None,
    ) -> Job:
        """
        Block until a job finishes. Raises JobTimeoutError if it takes too long.

        Args:
            job_id: The job ID to wait on.
            poll_interval: Seconds between status checks.
            timeout: Max seconds to wait before raising JobTimeoutError.
            on_progress: Optional callback called on every status update.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            job = self.status(job_id)

            if on_progress:
                on_progress(job)

            if job.status == "failure":
                raise JobFailedError(job.error or "Job failed with no error message")

            if job.status == "success":
                return job

            time.sleep(poll_interval)

        raise JobTimeoutError(f"Job {job_id} did not finish within {timeout}s")

    def fetch(self, job_id: str, output: str | Path | None = None) -> Path:
        """
        Download the output file of a completed job.

        Args:
            job_id: The job ID to fetch.
            output: File path to save to. Defaults to the filename from the server.

        Returns:
            Path to the saved file.
        """
        url = f"{self._base}/file/{job_id}"
        try:
            with httpx.stream("GET", url, headers=self._headers, timeout=self._timeout) as r:
                if r.status_code == 401:
                    raise AuthenticationError("Invalid API key")
                if r.status_code == 404:
                    raise JobNotFoundError("File not available or expired")
                if not r.is_success:
                    raise YTDownloadError(f"Download failed: {r.status_code}")

                if output is None:
                    cd = r.headers.get("content-disposition", "")
                    filename = "download"
                    if "filename=" in cd:
                        filename = cd.split("filename=")[-1].strip('"; \r\n')
                    output = Path(filename)

                output = Path(output)
                with open(output, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)

        except httpx.RequestError as e:
            raise YTDownloadError(f"Download request failed: {e}") from e

        return output

    def download(
        self,
        url: str,
        format: str = "mp4",
        quality: str = "best",
        output: str | Path | None = None,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        timeout: int = DEFAULT_TIMEOUT,
        on_progress: Callable[[Job], None] | None = None,
    ) -> Path:
        """
        Submit, wait, and fetch in one call.

        Args:
            url: YouTube URL to download.
            format: Output format — mp4, mp3, or webm.
            quality: Quality — best, 1080p, 720p, 480p, 360p, audio_only.
            output: Output file path. Defaults to the server filename.
            poll_interval: Seconds between status checks.
            timeout: Max seconds to wait.
            on_progress: Optional callback called on every status update.

        Returns:
            Path to the downloaded file.
        """
        job = self.submit(url, format=format, quality=quality)
        self.wait(job.id, poll_interval=poll_interval, timeout=timeout, on_progress=on_progress)
        return self.fetch(job.id, output=output)

    def delete(self, job_id: str) -> dict:
        """Delete a file from the server manually."""
        return self._request("DELETE", f"/file/{job_id}")
