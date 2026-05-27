"""Extract PDF attachments from new mail and submit them to Paperless."""

from __future__ import annotations

import email
import logging
from email.message import Message

import httpx

from mail_pipeline import notmuch

logger = logging.getLogger(__name__)

NOTMUCH_QUERY = "tag:inbox AND NOT tag:paperless AND mimetype:application/pdf"


def extract_pdfs(
    notmuch_config: str,
    paperless_url: str,
    paperless_token: str,
) -> int:
    """Submit unseen PDF attachments to Paperless and tag the message `+paperless`.

    Returns the number of messages from which at least one PDF was submitted.
    """
    message_ids = notmuch.search_message_ids(NOTMUCH_QUERY, notmuch_config)
    if not message_ids:
        return 0

    submitted_count = 0
    with httpx.Client(
        headers={"Authorization": f"Token {paperless_token}"},
        timeout=30.0,
    ) as client:
        for msg_id in message_ids:
            files = notmuch.message_files(msg_id, notmuch_config)
            if not files:
                logger.warning("No file on disk for notmuch %s", msg_id)
                continue

            if _submit_pdfs(files[0], client, paperless_url):
                notmuch.tag(msg_id, "+paperless", notmuch_config)
                submitted_count += 1

    return submitted_count


def _submit_pdfs(filepath: str, client: httpx.Client, paperless_url: str) -> bool:
    with open(filepath, "rb") as f:
        msg: Message = email.message_from_binary_file(f)

    submitted = False
    for part in msg.walk():
        if part.get_content_type() != "application/pdf":
            continue
        filename = part.get_filename() or "attachment.pdf"
        payload = part.get_payload(decode=True)
        if not payload:
            continue

        resp = client.post(
            f"{paperless_url}/api/documents/post_document/",
            files={"document": (filename, payload, "application/pdf")},
        )
        resp.raise_for_status()
        submitted = True

    return submitted
