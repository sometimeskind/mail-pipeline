"""Tests for mail_pipeline.notmuch — subprocess wrappers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mail_pipeline import notmuch


def test_index_mail_invokes_notmuch_new():
    with patch("mail_pipeline.notmuch.subprocess.run") as mock_run:
        notmuch.index_mail("/config/notmuch-config")

    args, kwargs = mock_run.call_args
    assert args[0] == ["notmuch", "new"]
    assert kwargs["check"] is True
    assert kwargs["env"]["NOTMUCH_CONFIG"] == "/config/notmuch-config"


def test_search_message_ids_returns_lines():
    completed = MagicMock(stdout="id:abc\nid:def\n\n")
    with patch("mail_pipeline.notmuch.subprocess.run", return_value=completed):
        ids = notmuch.search_message_ids("tag:inbox", "/config/nm")
    assert ids == ["id:abc", "id:def"]


def test_message_files_returns_lines():
    completed = MagicMock(stdout="/maildir/cur/1\n/maildir/cur/2\n")
    with patch("mail_pipeline.notmuch.subprocess.run", return_value=completed):
        files = notmuch.message_files("id:abc", "/config/nm")
    assert files == ["/maildir/cur/1", "/maildir/cur/2"]


def test_tag_invokes_notmuch_tag():
    with patch("mail_pipeline.notmuch.subprocess.run") as mock_run:
        notmuch.tag("id:abc", "+paperless", "/config/nm")

    args, kwargs = mock_run.call_args
    assert args[0] == ["notmuch", "tag", "+paperless", "id:abc"]
    assert kwargs["env"]["NOTMUCH_CONFIG"] == "/config/nm"
