import pytest
import httpx
from pytest_httpx import HTTPXMock
from yt_download_client import YTDownloadClient
from yt_download_client.exceptions import AuthenticationError, RateLimitError, JobFailedError, JobTimeoutError

BASE = "https://api.example.com"
KEY = "test-key"


@pytest.fixture
def client():
    return YTDownloadClient(base_url=BASE, api_key=KEY)


def test_health(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/health", json={"status": "ok", "active_downloads": 0})
    assert client.health()["status"] == "ok"


def test_submit(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/download",
        method="POST",
        json={"job_id": "abc-123", "status": "pending", "message": "queued"},
    )
    job = client.submit("https://youtu.be/test", format="mp4", quality="720p")
    assert job.id == "abc-123"
    assert job.status == "pending"


def test_status_success(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/status/abc-123",
        json={
            "job_id": "abc-123",
            "status": "success",
            "download_url": "/file/abc-123",
            "progress": {"title": "Test Video", "duration": 120, "filesize": 5000000},
        },
    )
    job = client.status("abc-123")
    assert job.successful
    assert job.done


def test_wait_success(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/status/abc-123",
        json={"job_id": "abc-123", "status": "progress", "progress": {"downloaded_bytes": 500}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/status/abc-123",
        json={"job_id": "abc-123", "status": "success", "download_url": "/file/abc-123", "progress": {}},
    )
    job = client.wait("abc-123", poll_interval=0)
    assert job.successful


def test_wait_failure(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/status/abc-123",
        json={"job_id": "abc-123", "status": "failure", "error": "Video unavailable"},
    )
    with pytest.raises(JobFailedError, match="Video unavailable"):
        client.wait("abc-123", poll_interval=0)


def test_wait_timeout(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/status/abc-123",
        json={"job_id": "abc-123", "status": "pending"},
    )
    with pytest.raises(JobTimeoutError):
        client.wait("abc-123", poll_interval=0, timeout=0)


def test_auth_error(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/health", status_code=401)
    with pytest.raises(AuthenticationError):
        client.health()


def test_rate_limit_error(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/download",
        method="POST",
        status_code=429,
        headers={"Retry-After": "30"},
    )
    with pytest.raises(RateLimitError):
        client.submit("https://youtu.be/test")
