# Local security review — 2026-11-13

## Outcome

The reviewed client changes pass **45 regression/security tests on Python 3.13 and Python 3.11**, static security/lint/format checks and wheel/sdist builds. Resolved Python dependencies have no known advisories reported by pip-audit on the review date. The API/container residual risks are documented in the [API security review](https://github.com/HkrUchiwa2011/yt-download-api/blob/main/SECURITY_REVIEW.md).

## Changes verified

- Shared HTTP session with explicit close/context manager; credentials excluded from error messages; no redirects or environment proxy inheritance.
- Bounded safe-GET retries and Retry-After values, monotonic wait deadlines, no automatic POST/DELETE retries and strict job path segments.
- Identity encoding required before reading, preventing decompression bombs; bounded JSON and file responses, consistent status/parse/network errors and nullable duration metadata.
- RFC filename parsing with path/control/reserved-name checks, private temporary transfers, no overwrite of implicit destinations/symlinks, atomic replacement only for explicitly chosen outputs, cleanup after interrupted transfers and incomplete/oversized response rejection.
- Real API/SDK downloads of Creative Commons Big Buck Bunny succeeded as MP4 (46,283,921 bytes), MP3 (15,232,463 bytes) and WebM (34,312,454 bytes) against the updated Docker native stack. Expected streams were checked with production ffprobe, repeated retrieval matched and server-side deletion succeeded for each format.

## Boundaries

The configured server is trusted to authenticate correctly and serve the intended video. HTTPS is required outside a trusted local network. A caller-supplied output path intentionally authorizes replacement of that destination after a successful transfer; server-supplied paths do not. There is no total wall-clock deadline for the entire submit/wait/file-transfer operation: wait has a deadline and individual HTTP operations have network timeouts. A persistent slow file stream can last longer than one network timeout, but response size and retry counts are bounded.

This library does not provide user accounts, tenant isolation, automatic retries of job submission, or HTTP range/resume. The Discord example uses asyncio.to_thread so synchronous polling does not block the bot event loop.
