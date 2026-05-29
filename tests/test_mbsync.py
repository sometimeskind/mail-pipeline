"""Tests for mail_pipeline.mbsync — subprocess wrapper around mbsync."""

from __future__ import annotations

import logging
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from mail_pipeline import mbsync


def test_run_mbsync_invokes_mbsync_with_config_and_channel():
    completed = MagicMock(stdout="", stderr="")
    with patch("mail_pipeline.mbsync.subprocess.run", return_value=completed) as mock_run:
        mbsync.run_mbsync("/config/mbsyncrc")

    args, kwargs = mock_run.call_args
    assert args[0] == ["mbsync", "-c", "/config/mbsyncrc", "proton"]
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True


def test_run_mbsync_logs_captured_output_on_failure(caplog):
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["mbsync", "-c", "/config/mbsyncrc", "proton"],
        output="some stdout",
        stderr="IMAP auth failed",
    )
    with patch("mail_pipeline.mbsync.subprocess.run", side_effect=error):
        with caplog.at_level(logging.ERROR, logger="mail_pipeline.mbsync"):
            with pytest.raises(subprocess.CalledProcessError):
                mbsync.run_mbsync("/config/mbsyncrc")

    assert any(
        "IMAP auth failed" in record.message and "some stdout" in record.message
        for record in caplog.records
    )
