# Changelog

## 1.1.0 — unreleased

- Reusable HTTP session with close/context manager support.
- Bounded safe-GET retries and Retry-After handling; submission is never retried automatically.
- Monotonic polling deadline, consistent exceptions and bounded JSON/file responses.
- Safe Content-Disposition parsing, path validation and atomic transfers; default destinations never overwrite files.
- Nullable metadata duration, corrected repository metadata and nonblocking Discord usage example.
- Locked local dependencies and security regression tests.

### Migration from 1.0.1

HTTPX 0.28.1 is the tested minimum. Close clients when finished. Reusing an existing server-derived filename now raises YTDownloadError; choose an explicit output if you intend to replace a file. HTTP redirects and environment proxy settings are disabled. API response bodies and request URLs are omitted from error messages to avoid leaking credentials. Unknown video durations are represented as None.
