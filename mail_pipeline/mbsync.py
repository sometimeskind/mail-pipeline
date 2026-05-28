"""Subprocess wrapper around `mbsync`."""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


def run_mbsync(mbsync_config: str, channel: str = "proton") -> None:
    started = time.perf_counter()
    result = subprocess.run(
        ["mbsync", "-c", mbsync_config, channel],
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - started

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        logger.info("mbsync stdout (%s, %.2fs):\n%s", channel, elapsed, stdout)
    else:
        logger.info("mbsync %s finished in %.2fs (no stdout)", channel, elapsed)
    if stderr:
        logger.info("mbsync stderr:\n%s", stderr)
