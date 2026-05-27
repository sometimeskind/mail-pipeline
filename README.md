# mail-pipeline

Dockerized mail pipeline: Proton Bridge IMAP ↔ `mbsync` ↔ Maildir → `notmuch` index → PDF attachments to Paperless.

```
Proton ↔ Bridge ↔ mbsync ↔ /maildir ↔ Dovecot ↔ Thunderbird (or any IMAP client)
                              ↓
                           notmuch
                              ↓
                       extract PDFs → Paperless
                              ↓
                         push metrics → Pushgateway
```

`mbsync` is **bidirectional**. New mail flows down from Proton; local changes (deletes, moves, flag/Seen changes made by a mail client through Dovecot) flow back up on the next sync. A single long-running container runs a Prefect flow on a configurable schedule (default every 5 minutes) and exposes a small HTTP API for health probes and on-demand triggers.

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

## Bidirectional architecture (Dovecot + IMAP client)

`/maildir` is meant to be shared with a Dovecot sidecar so a mail client (e.g. Thunderbird) can read and write the same store. The expected layout:

```
Proton ↔ Bridge ↔ [this container: mbsync + notmuch + extract]
                          ↕
                       /maildir   (shared PVC)
                          ↕
                  [sidecar: Dovecot IMAP]
                          ↕
                    Thunderbird / mutt / …
```

### Concurrency

`mbsync` and Dovecot both write `/maildir`. Each handles its own atomic-rename and Maildir-level locking; they are designed to coexist. No flock or coordination from this codebase is required.

### Flag synchronisation

For Thunderbird's read/unread/flagged state to round-trip back to Proton, the cluster's `notmuch-config` should set `maildir.synchronize_flags = true`. The chain becomes:

```
Thunderbird marks read
  → Dovecot writes the `S` flag into the Maildir filename
  → next `notmuch new` reflects the flag in notmuch's DB
  → next `mbsync` syncs the flag to Bridge → Proton
```

Inbound flag changes (e.g. read on the Proton web UI) flow the same way in reverse.

### `+paperless` does not propagate to Proton

The `+paperless` tag is written only to notmuch's database — it is a local marker so already-processed messages are not re-submitted. It is **not** visible in Thunderbird or as a Proton label. Surfacing it requires a custom Maildir keyword mapped to a synchronisable flag in both `notmuch-config` and `mbsyncrc`; that mapping lives in the cluster, not in this image.

### Outbound latency

Local changes (Thunderbird → Dovecot → Maildir) propagate to Proton on the next `mail` flow run — at most `FETCH_CRON` minutes (default 5). For lower latency, the cluster can run a separate Maildir-watching sidecar (e.g. `inotifywait` on `/maildir`) that calls `POST /sync/trigger` on local writes — the outbound mirror of the inbound goimapnotify pattern.

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
