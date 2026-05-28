"""Extract PDF attachments from new mail and submit them to Paperless."""

from __future__ import annotations

import email
import logging
import time
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
    logger.info(
        "extract: %d candidate message(s) match query %r",
        len(message_ids), NOTMUCH_QUERY,
    )
    if not message_ids:
        return 0

    submitted_count = 0
    skipped_no_file = 0
    skipped_no_pdf = 0
    pdf_count = 0
    total_bytes = 0
    started = time.perf_counter()

    with httpx.Client(
        headers={"Authorization": f"Token {paperless_token}"},
        timeout=30.0,
    ) as client:
        for msg_id in message_ids:
            files = notmuch.message_files(msg_id, notmuch_config)
            if not files:
                logger.warning("No file on disk for notmuch %s", msg_id)
                skipped_no_file += 1
                continue

            logger.info(
                "extract: processing %s (%d file(s) on disk, using %s)",
                msg_id, len(files), files[0],
            )
            n, bytes_ = _submit_pdfs(files[0], client, paperless_url)
            if n:
                notmuch.tag(msg_id, "+paperless", notmuch_config)
                submitted_count += 1
                pdf_count += n
                total_bytes += bytes_
            else:
                logger.info("extract: no PDF parts found in %s", msg_id)
                skipped_no_pdf += 1

    elapsed = time.perf_counter() - started
    logger.info(
        "extract: submitted %d PDF(s) totalling %s from %d message(s) in %.2fs"
        " (skipped: %d no-file, %d no-pdf-part)",
        pdf_count, _human_size(total_bytes), submitted_count, elapsed,
        skipped_no_file, skipped_no_pdf,
    )
    return submitted_count


def _submit_pdfs(
    filepath: str, client: httpx.Client, paperless_url: str,
) -> tuple[int, int]:
    """Return (number of PDFs submitted, total bytes)."""
    with open(filepath, "rb") as f:
        msg: Message = email.message_from_binary_file(f)

    count = 0
    total = 0
    for part in msg.walk():
        if part.get_content_type() != "application/pdf":
            continue
        filename = part.get_filename() or "attachment.pdf"
        payload = part.get_payload(decode=True)
        if not payload:
            logger.warning("  PDF part %r had empty payload, skipping", filename)
            continue

        size = len(payload)
        logger.info("  -> submitting PDF %r (%s) to Paperless", filename, _human_size(size))
        post_started = time.perf_counter()
        resp = client.post(
            f"{paperless_url}/api/documents/post_document/",
            files={"document": (filename, payload, "application/pdf")},
        )
        resp.raise_for_status()
        logger.info(
            "     paperless accepted %r: HTTP %d in %.2fs",
            filename, resp.status_code, time.perf_counter() - post_started,
        )
        count += 1
        total += size

    return count, total


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
