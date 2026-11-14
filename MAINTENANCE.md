# Maintenance

GitHub Actions runs on pull requests, pushes to `main`, manual dispatch, and
Mondays at 06:43 UTC. It tests Python 3.11 and 3.13, checks lint/formatting,
audits installed dependencies and builds the wheel/source distribution. Tests
use mocked HTTP responses and do not contact YouTube. Actions are pinned and
jobs have read-only repository permissions.

Dependabot proposes weekly uv and GitHub Actions updates on Mondays at 06:00 UTC.
Compatible Python updates are grouped; major changes remain separate. Security
updates may arrive outside that schedule. There is no automatic merge or PyPI
publication. GitHub may disable scheduled workflows after 60 days without
repository activity; check their status during inactive periods.

For each pull request:

1. Review release notes, compatibility and security advisories.
2. Run `uv sync --locked --extra dev` with the uv version pinned in CI.
3. Wait for both Python jobs and distribution builds to pass.
4. For changes to request, polling or transfer behavior, also verify the client
   against a running API. Confirm that failures preserve existing output files
   and that submission is never silently retried.
5. Update `CHANGELOG.md` before publishing a release and check package version,
   metadata and included files. Publish to PyPI only after manual validation.

The API maintains its native/container advisories separately; see
[its maintenance guide](https://github.com/HkrUchiwa2011/yt-download-api/blob/main/MAINTENANCE.md).
