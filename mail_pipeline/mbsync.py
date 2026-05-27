"""Subprocess wrapper around `mbsync`."""

from __future__ import annotations

import subprocess


def run_mbsync(mbsync_config: str, channel: str = "proton") -> None:
    subprocess.run(["mbsync", "-c", mbsync_config, channel], check=True)
