"""Tests for mail_pipeline.extract — PDF extraction and Paperless submission."""

from __future__ import annotations

from email.message import EmailMessage
from unittest.mock import patch

import httpx
import respx

from mail_pipeline import extract


def _make_pdf_message() -> bytes:
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "me@example.com"
    msg["Subject"] = "Invoice"
    msg["Message-ID"] = "<abc123@example.com>"
    msg.set_content("See attached invoice.")
    msg.add_attachment(
        b"%PDF-1.4 sample bytes",
        maintype="application",
        subtype="pdf",
        filename="invoice.pdf",
    )
    return bytes(msg)


@respx.mock
def test_extract_pdfs_submits_and_tags(tmp_path):
    mail_file = tmp_path / "1.eml"
    mail_file.write_bytes(_make_pdf_message())

    route = respx.post("http://paperless/api/documents/post_document/").mock(
        return_value=httpx.Response(200)
    )

    with patch("mail_pipeline.extract.notmuch.search_message_ids", return_value=["id:abc123"]), \
         patch("mail_pipeline.extract.notmuch.message_files", return_value=[str(mail_file)]), \
         patch("mail_pipeline.extract.notmuch.tag") as mock_tag:
        count = extract.extract_pdfs(
            notmuch_config="/dev/null",
            paperless_url="http://paperless",
            paperless_token="tok",
        )

    assert count == 1
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Token tok"
    body = sent.content
    assert b"invoice.pdf" in body
    assert b"%PDF-1.4 sample bytes" in body
    mock_tag.assert_called_once_with("id:abc123", "+paperless", "/dev/null")


def test_extract_pdfs_no_messages_returns_zero():
    with patch("mail_pipeline.extract.notmuch.search_message_ids", return_value=[]):
        count = extract.extract_pdfs(
            notmuch_config="/dev/null",
            paperless_url="http://paperless",
            paperless_token="tok",
        )
    assert count == 0


@respx.mock
def test_extract_pdfs_skips_messages_with_no_pdf_part(tmp_path):
    msg = EmailMessage()
    msg["Subject"] = "no attachments"
    msg.set_content("plain text only")
    mail_file = tmp_path / "1.eml"
    mail_file.write_bytes(bytes(msg))

    with patch("mail_pipeline.extract.notmuch.search_message_ids", return_value=["id:xyz"]), \
         patch("mail_pipeline.extract.notmuch.message_files", return_value=[str(mail_file)]), \
         patch("mail_pipeline.extract.notmuch.tag") as mock_tag:
        count = extract.extract_pdfs(
            notmuch_config="/dev/null",
            paperless_url="http://paperless",
            paperless_token="tok",
        )

    assert count == 0
    mock_tag.assert_not_called()


def test_extract_pdfs_skips_when_no_file_on_disk():
    with patch("mail_pipeline.extract.notmuch.search_message_ids", return_value=["id:abc"]), \
         patch("mail_pipeline.extract.notmuch.message_files", return_value=[]), \
         patch("mail_pipeline.extract.notmuch.tag") as mock_tag:
        count = extract.extract_pdfs(
            notmuch_config="/dev/null",
            paperless_url="http://paperless",
            paperless_token="tok",
        )

    assert count == 0
    mock_tag.assert_not_called()
