"""Subprocess wrappers around the `notmuch` CLI."""

from __future__ import annotations

import os
import subprocess


def _env(notmuch_config: str) -> dict[str, str]:
    return {**os.environ, "NOTMUCH_CONFIG": notmuch_config}


def index_mail(notmuch_config: str) -> None:
    """Run `notmuch new` to index any newly synced messages."""
    subprocess.run(["notmuch", "new"], check=True, env=_env(notmuch_config))


def search_message_ids(query: str, notmuch_config: str) -> list[str]:
    """Return notmuch message identifiers (one `id:<hash>` per match)."""
    result = subprocess.run(
        ["notmuch", "search", "--output=messages", query],
        capture_output=True, text=True, check=True, env=_env(notmuch_config),
    )
    return [line for line in result.stdout.strip().splitlines() if line]


def message_files(message_id: str, notmuch_config: str) -> list[str]:
    """Return on-disk file paths for *message_id* (`id:<hash>` form)."""
    result = subprocess.run(
        ["notmuch", "search", "--output=files", message_id],
        capture_output=True, text=True, check=True, env=_env(notmuch_config),
    )
    return [line for line in result.stdout.strip().splitlines() if line]


def tag(message_id: str, tag_expr: str, notmuch_config: str) -> None:
    """Apply *tag_expr* (e.g. `+paperless`) to *message_id*."""
    subprocess.run(
        ["notmuch", "tag", tag_expr, message_id],
        check=True, env=_env(notmuch_config),
    )
