import httpx
import pytest

from yt_download_client import JobTimeoutError, ServerBusyError, YTDownloadClient, YTDownloadError
from yt_download_client.client import _retry_after

BASE = "https://api.example.org"


@pytest.fixture
def client():
    with YTDownloadClient(BASE, "key", max_retries=0) as client:
        yield client


@pytest.mark.parametrize(
    "filename",
    [
        "/etc/passwd",
        "../secret",
        "..\\secret",
        "C:\\secret",
        ".env",
        "CON",
        "x:y",
        "name/other",
        "file.",
    ],
)
def test_unsafe_server_filename_rejected(client, filename, tmp_path, monkeypatch, httpx_mock):
    monkeypatch.chdir(tmp_path)
    httpx_mock.add_response(
        url=f"{BASE}/file/job",
        content=b"payload",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    with pytest.raises(YTDownloadError, match="unsafe filename"):
        client.fetch("job")
    assert not list(tmp_path.iterdir())


def test_rfc5987_filename_supported(client, tmp_path, monkeypatch, httpx_mock):
    monkeypatch.chdir(tmp_path)
    httpx_mock.add_response(
        url=f"{BASE}/file/job",
        content=b"payload",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''vid%C3%A9o.mp4"},
    )
    path = client.fetch("job")
    assert path.name == "vidéo.mp4"
    assert path.read_bytes() == b"payload"


def test_rfc5987_traversal_rejected(client, tmp_path, monkeypatch, httpx_mock):
    monkeypatch.chdir(tmp_path)
    httpx_mock.add_response(
        url=f"{BASE}/file/job",
        content=b"payload",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''..%2Fsecret"},
    )
    with pytest.raises(YTDownloadError):
        client.fetch("job")
    assert not list(tmp_path.iterdir())


def test_default_destination_not_overwritten(client, tmp_path, monkeypatch, httpx_mock):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "video.mp4"
    target.write_bytes(b"existing")
    httpx_mock.add_response(
        url=f"{BASE}/file/job",
        content=b"new",
        headers={"Content-Disposition": 'attachment; filename="video.mp4"'},
    )
    with pytest.raises(YTDownloadError):
        client.fetch("job")
    assert target.read_bytes() == b"existing"
    assert list(tmp_path.iterdir()) == [target]


def test_default_destination_symlink_not_followed(client, tmp_path, monkeypatch, httpx_mock):
    monkeypatch.chdir(tmp_path)
    secret = tmp_path / "secret"
    secret.write_bytes(b"private")
    (tmp_path / "video.mp4").symlink_to(secret)
    httpx_mock.add_response(
        url=f"{BASE}/file/job",
        content=b"new",
        headers={"Content-Disposition": 'attachment; filename="video.mp4"'},
    )
    with pytest.raises(YTDownloadError):
        client.fetch("job")
    assert secret.read_bytes() == b"private"


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b"partial"
        raise httpx.ReadError("interrupted")


def test_interrupted_transfer_preserves_explicit_destination(client, tmp_path, httpx_mock):
    target = tmp_path / "video.mp4"
    target.write_bytes(b"existing")
    httpx_mock.add_response(url=f"{BASE}/file/job", stream=BrokenStream())
    with pytest.raises(YTDownloadError):
        client.fetch("job", output=target)
    assert target.read_bytes() == b"existing"
    assert list(tmp_path.iterdir()) == [target]


def test_stream_can_retry_without_corrupting_file(tmp_path, httpx_mock, monkeypatch):
    monkeypatch.setattr("yt_download_client.client.time.sleep", lambda _: None)
    httpx_mock.add_response(url=f"{BASE}/file/job", stream=BrokenStream())
    httpx_mock.add_response(url=f"{BASE}/file/job", content=b"complete")
    with YTDownloadClient(BASE, "key", max_retries=1) as client:
        target = client.fetch("job", tmp_path / "video.mp4")
    assert target.read_bytes() == b"complete"
    assert list(tmp_path.iterdir()) == [target]


def test_short_transfer_not_committed(client, tmp_path, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/file/job", content=b"short", headers={"Content-Length": "50"}
    )
    with pytest.raises(YTDownloadError, match="Incomplete"):
        client.fetch("job", tmp_path / "video.mp4")
    assert not list(tmp_path.iterdir())


def test_download_size_limit(tmp_path, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/file/job", content=b"12345")
    with YTDownloadClient(BASE, "key", max_retries=0, max_download_bytes=4) as client:
        with pytest.raises(YTDownloadError, match="size limit"):
            client.fetch("job", tmp_path / "video.mp4")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "identifier", ["../health", "job/other", "%2fsecret", "", "x?key=secret", "x#fragment"]
)
def test_job_identifiers_cannot_change_request_path(client, identifier, httpx_mock):
    with pytest.raises(ValueError):
        client.status(identifier)
    assert not httpx_mock.get_requests()


def test_redirect_cannot_leak_key(client, tmp_path, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/file/job", status_code=302, headers={"Location": "https://evil.org/file"}
    )
    with pytest.raises(YTDownloadError):
        client.fetch("job", tmp_path / "video.mp4")
    assert len(httpx_mock.get_requests()) == 1


def test_submission_never_retried(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/download", status_code=503, headers={"Retry-After": "10"})
    with YTDownloadClient(BASE, "key") as client:
        with pytest.raises(ServerBusyError) as error:
            client.submit("https://youtu.be/BaW_jenozKc")
    assert error.value.retry_after == 10
    assert len(httpx_mock.get_requests()) == 1


def test_retry_after_respects_wait_deadline(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/status/job", status_code=429, headers={"Retry-After": "60"}
    )
    with YTDownloadClient(BASE, "key") as client:
        with pytest.raises(JobTimeoutError):
            client.wait("job", timeout=0.1)
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("value", ["nan", "inf", "-4", "invalid"])
def test_retry_after_never_unbounded(value):
    response = httpx.Response(429, headers={"Retry-After": value})
    assert 0 <= _retry_after(response) <= 300


def test_invalid_json_wrapped(client, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/health", text="invalid")
    with pytest.raises(YTDownloadError, match="invalid JSON"):
        client.health()


def test_json_response_size_bounded(client, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/health", content=b"x" * (1024**2 + 1))
    with pytest.raises(YTDownloadError, match="size limit"):
        client.health()


def test_unknown_status_wrapped(client, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/status/job", json={"job_id": "job", "status": "unknown"})
    with pytest.raises(YTDownloadError, match="invalid job"):
        client.status("job")


def test_unknown_duration_supported(client, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/info?url=test", json={"title": "Live", "duration": None})
    assert client.info("test").duration_formatted == "unknown"


def test_context_manager_closes_session():
    with YTDownloadClient(BASE, "key") as client:
        assert not client._client.is_closed
    assert client._client.is_closed


@pytest.mark.parametrize("path,fetch", [("/health", False), ("/file/job", True)])
def test_unexpected_compression_rejected_before_reading(client, httpx_mock, tmp_path, path, fetch):
    class MustNotRead(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("Compressed response must be rejected before decoding")
            yield b""

    httpx_mock.add_response(
        url=BASE + path, headers={"Content-Encoding": "gzip"}, stream=MustNotRead()
    )
    with pytest.raises(YTDownloadError, match="Encoded"):
        if fetch:
            client.fetch("job", tmp_path / "video.mp4")
        else:
            client.health()
    assert not list(tmp_path.iterdir())
    assert httpx_mock.get_request().headers["Accept-Encoding"] == "identity"
