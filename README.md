# mail-pipeline

Dockerized mail pipeline: Proton Bridge IMAP → `mbsync` → Maildir → `notmuch` index → PDF attachments to Paperless.

```
Proton Bridge IMAP → mbsync → /maildir → notmuch → extract PDFs → Paperless
                                                  → push metrics → Pushgateway
```

A single long-running container runs a Prefect flow on a configurable schedule (default every 5 minutes) and exposes a small HTTP API for health probes and on-demand triggers.

| Flow | Default schedule | Tasks |
|---|---|---|
| `mail` | `*/5 * * * *` (`FETCH_CRON`) | `sync_mail` → `index_mail` → `extract_pdfs` → `push_metrics` |

## HTTP API (port `8080`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | open | k8s liveness/readiness probe |
| `POST` | `/sync/trigger` | bearer | Submit a `mail` flow run and return 202 |

`/sync/trigger` and the cron schedule both submit runs of the same Prefect deployment. Overlapping runs are coalesced by a Prefect named concurrency limit (`mail-pipeline`, `occupy=1`, `timeout_seconds=0`) — a second run that finds the slot taken exits immediately rather than queuing.

## IMAP IDLE / sidecar integration

This image is the **primary container only**. It does not include an IMAP IDLE watcher. The Kubernetes manifests (in `sometimeskind/homelab`) are responsible for any sidecar (e.g. `goimapnotify`) that watches Bridge IMAP and triggers near-real-time syncs.

The integration contract is the HTTP API: the sidecar's `onNewMail` hook runs

```sh
curl -X POST http://localhost:8080/sync/trigger \
     -H "Authorization: Bearer $API_BEARER_TOKEN"
```

No shared volumes, lock files, or other in-pod coordination are required. Prefect handles coalescing.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `PREFECT_API_URL` | yes | — | Prefect server URL |
| `PAPERLESS_URL` | yes | — | Paperless base URL |
| `PAPERLESS_API_TOKEN` | yes | — | Paperless API token |
| `API_BEARER_TOKEN` | yes | — | Bearer token guarding `/sync/trigger` |
| `FETCH_CRON` | no | `*/5 * * * *` | Cron schedule for the deployment |
| `PUSHGATEWAY_URL` | no | unset → metrics skipped | Pushgateway URL |
| `NOTMUCH_CONFIG` | no | `/config/notmuch-config` | Path to notmuch config |
| `MBSYNC_CONFIG` | no | `/config/mbsyncrc` | Path to mbsync config |

## Volume mounts expected by the image

| Path | Purpose |
|---|---|
| `/maildir/` | Maildir — mbsync writes here, notmuch indexes here |
| `/state/` | Reserved for future use |
| `/config/mbsyncrc` | mbsync config |
| `/config/notmuch-config` | notmuch config |
| `/secrets/bridge-imap-password/password` | Bridge IMAP password (referenced from `mbsyncrc`) |

## Local development

```bash
pip install -r requirements.txt -r requirements-dev.txt -e .
pytest tests/
```

Build and run the dev image to exercise tests against the installed `mbsync` and `notmuch`:

```bash
docker build --target dev -t mail-pipeline:dev .
docker run --rm mail-pipeline:dev
```

## CI

`.github/workflows/ci.yml` runs tests, builds the image, runs health checks against the built image, and on push to `main` pushes `ghcr.io/<owner>/mail-pipeline:{latest,<sha>}`.

## Bumping dependencies

Dependabot (`.github/dependabot.yml`) handles weekly bumps for:

- Python deps in `requirements.txt` and `requirements-dev.txt`
- The `FROM python:3.13-slim` base image
- GitHub Actions versions
