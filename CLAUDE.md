# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small FastAPI service that the Fragalysis Stack calls to convert a **username** into a set of
**Target Access Strings** (TAS) such as `lb12345-1` (`<proposalCode><proposalNumber>-<sessionNumber>`).
It obtains them from a remote ISPyB MySQL database over an SSH tunnel and caches them in memcached.

`README.md` documents the API contract other implementations must honour
(`/version/`, `/ping/`, `/target-access/{username}`); `DESIGN.md` documents the caching rules and
the full set of `TAA_*` environment variables. Both are the source of truth — keep them in step with
behaviour changes.

## Commands

Set-up (Poetry, Python 3.12):

    poetry install --with dev
    pre-commit install -t commit-msg -t pre-commit

Lint / format / type-check — everything runs through pre-commit (isort, black, mypy, pylint);
there is no separate lint script:

    pre-commit run --all-files
    pre-commit run mypy --all-files      # a single hook

Run locally (builds the image and starts memcached alongside it):

    docker compose up --build --detach                                  # SSH password
    docker compose --file docker-compose-private-key.yml up --build -d  # SSH private key
    docker compose down

Environment values come from a git-ignored `.env` file consumed by `base-services.yml`.

Query the running service (the query key is hard-coded to `blob1234` in `base-services.yml`):

    http localhost:8080/target-access/abc 'x-taaquerykey:blob1234'
    http localhost:8080/ping/
    http localhost:8080/version/

## Testing policy — no TDD in this repository

**Do not write unit tests here, and do not add a test framework.** This overrides any general
test-first/TDD instruction.

Almost everything this service does is an interaction with something it does not own — a remote
ISPyB MySQL database over an SSH tunnel, and a memcached container in the same Pod. Unit tests
around that either need mocks of the very behaviour we are unsure about (which is what the ISPyB
stored procedures return), or they end up asserting the shape of the `ispyb` package rather than
anything about this service. Neither tells us whether a change works.

Changes are verified **in-situ** instead:

- `docker compose up --build` locally, then exercise `/version/`, `/ping/` and
  `/target-access/{username}` (see the commands above), plus the in-container `stats.py`,
  `tas.py`, `get.py` and `clear.py` utilities.
- Against a real ISPyB, with credentials, in a deployed environment. A local run with no
  `TAA_ISPYB_*` configuration will log *"Insufficient configuration to establish ISPyB
  connections"*, report `/ping` as `NOT OK` and return empty target-access sets — that is expected,
  and it means the ISPyB path has **not** been exercised.

Be explicit in reporting which of those two levels a change has actually been through.

## Architecture

- `app/app.py` — two *separate* FastAPI applications in one module: `auth` (the in-cluster API,
  port 8080) and `stats` (the customer-facing text/plain stats endpoint, port 8081).
  `docker-entrypoint.sh` launches a uvicorn process for each.
- `app/common.py` — memcached client factory, cache key names/prefixes, and `TaSerde`, the custom
  serializer that stores sets via `repr()`/`eval()` and datetimes as strings, tagged by flag value.
  Changing a flag number breaks every existing cached record.
- `app/remote_ispyb_connector.py` — `SSHConnector`, copied from the Fragalysis stack's original
  `security` module. Subclasses the `ispyb` package connector and builds an `sshtunnel` +
  `pymysql` connection, retrying `OperationalError` (see `PYMYSQL_OE_RECONNECT_ATTEMPTS`).
- `app/stats.py` — builds the stats dictionary. It enumerates cached users by shelling out to
  `memdump -s localhost` (the `libmemcached` package installed in the Dockerfile), so stats only
  work inside the container.
- `app/prometheus_metrics.py` — counters incremented by the connector. Nothing currently exposes a
  `/metrics` endpoint, so these are collected but not scraped.
- `app/config.py` — every environment variable is read here, at import time, into `Config` class
  attributes. Tests or tools that need different config must set the environment before import.

Cache keys share one memcached namespace: a URL-encoded username holds the TAS set, and
`timestamp-{encoded-username}` holds the collection time. `valid_encoded_username()` rejects
usernames that would collide with reserved counter keys or the `timestamp-` prefix — extend
`INVALID_USERNAMES` in `common.py` if you add a new well-known key.

### Import-time side effects in `app/app.py`

Importing the module (i.e. every uvicorn worker start) reads `logging.config` **relative to the
working directory**, resets the ping/query counters in memcached to zero, and — when
`TAA_ENABLE_DAVE_LISTER=yes` — injects the fake user `dave lister`. So statistics are per-process-start,
not lifetime.

### The `VERSION` file

`app.py` reads a file called `VERSION` at import time and serves it from `/version/`. That file does
not exist in the repository — the Dockerfile writes it from the `VERSION` build argument. Running
uvicorn outside a container therefore fails unless you create a `VERSION` file first (it is
excluded from the `end-of-file-fixer` hook).

## Release / CI

- `.github/workflows/latest.yaml` builds and pushes an image on every branch push — `:latest`
  from the default branch, and `:<branch-name>` from any other branch. The branch name is
  slugified (`rlespinasse/github-slug-action`) because image tags cannot contain `/`, so
  `build/upgrade-ispyb-12` publishes `:build-upgrade-ispyb-12`. Note the branch filter is `'**'`,
  not `'*'` — the latter does not match branch names containing `/`.
- `.github/workflows/tag.yaml` fires on a git tag, pushes an image tagged with the git tag, and
  passes `VERSION=<tag>` as a build argument — so **the git tag is what `/version/` reports**.
  Tags are semver without a `v` prefix (`1.0.0`).

## Conventions

- Commitizen / Conventional Commits are enforced by the `commit-msg` hook.
- Pylint is configured in *both* `.pylintrc` and `pyproject.toml`; `.pylintrc` takes precedence.
  Change the one that is actually in effect, or keep them consistent.
- The code is fully type-annotated (mypy runs with `--check-untyped-defs`); match that style.
