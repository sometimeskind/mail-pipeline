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

`mbsync` is **bidirectional**. New mail flows down from Proton; local changes (deletes, moves, flag/Seen changes made by a mail client through Dovecot) flow back up. A single long-running container runs a Prefect flow on event-driven triggers from the cluster (with a cron-backstop) and exposes a small HTTP API for health probes and on-demand triggers — see [Trigger architecture](#trigger-architecture).

| Flow | Backstop schedule | Tasks |
|---|---|---|
| `mail` | `*/5 * * * *` (`FETCH_CRON`) | `sync_mail` → `index_mail` → `extract_pdfs` → `push_metrics` |

## HTTP API (port `8080`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | open | k8s liveness/readiness probe |
| `POST` | `/sync/trigger` | bearer | Submit a `mail` flow run and return 202 |

`/sync/trigger` and the cron schedule both submit runs of the same Prefect deployment. Overlapping runs are coalesced by a Prefect named concurrency limit (`mail-pipeline`, `occupy=1`, `timeout_seconds=0`) — a second run that finds the slot taken exits immediately rather than queuing.

## Trigger architecture

The `mail` flow is intended to run on **event-driven triggers** from two cluster-side sidecars. The cron schedule is a backstop, not the primary mechanism.

| Trigger | Direction | How | Latency |
|---|---|---|---|
| `goimapnotify` sidecar | Inbound (Proton → `/maildir`) | Watches Bridge over IMAP IDLE; on new mail, calls `POST /sync/trigger` | Near real-time |
| `inotifywait` sidecar | Outbound (`/maildir` → Proton) | Watches `/maildir` for local writes (Dovecot, mail clients); on change, calls `POST /sync/trigger` | Near real-time |
| Cron (`FETCH_CRON`) | Both | Submits a flow run regardless of activity | Up to `FETCH_CRON` minutes |

The sidecars themselves live in the cluster (`sometimeskind/homelab`), not this image. The integration contract is just the HTTP API:

```sh
curl -X POST http://localhost:8080/sync/trigger \
     -H "Authorization: Bearer $API_BEARER_TOKEN"
```

Overlapping triggers are coalesced by a Prefect named concurrency limit (`mail-pipeline`, `occupy=1`, `timeout_seconds=0`); a second run that finds the slot taken exits immediately and the next trigger or cron tick picks up any missed work. Fire `/sync/trigger` as often as you like.

`FETCH_CRON` defaults to `*/5 * * * *` so that a sidecar restart, crash, or network blip is caught within 5 minutes. With both sidecars reliable, raising this (e.g. `0 * * * *`) is safe.

No shared volumes, lock files, or other in-pod coordination are required.

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

### Outbound trigger

Local changes (Thunderbird → Dovecot → `/maildir`) propagate to Proton when the cluster's `inotifywait` sidecar sees the write and calls `POST /sync/trigger`. See [Trigger architecture](#trigger-architecture).

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
