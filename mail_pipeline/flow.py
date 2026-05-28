"""Prefect tasks and flow for the mail pipeline."""

from __future__ import annotations

import os
import time

from prefect import flow, get_run_logger, task
from prefect.concurrency.sync import concurrency

from mail_pipeline import extract, mbsync, metrics, notmuch


def _notmuch_config() -> str:
    return os.environ.get("NOTMUCH_CONFIG", "/config/notmuch-config")


def _mbsync_config() -> str:
    return os.environ.get("MBSYNC_CONFIG", "/config/mbsyncrc")


@task(name="sync-mail", log_prints=True)
def sync_mail_task() -> None:
    logger = get_run_logger()
    started = time.perf_counter()
    mbsync.run_mbsync(_mbsync_config())
    logger.info("sync-mail complete in %.2fs", time.perf_counter() - started)


@task(name="index-mail", log_prints=True)
def index_mail_task() -> None:
    logger = get_run_logger()
    started = time.perf_counter()
    notmuch.index_mail(_notmuch_config())
    logger.info("index-mail complete in %.2fs", time.perf_counter() - started)


@task(name="extract-pdfs", log_prints=True)
def extract_pdfs_task() -> None:
    logger = get_run_logger()
    started = time.perf_counter()
    submitted = extract.extract_pdfs(
        notmuch_config=_notmuch_config(),
        paperless_url=os.environ["PAPERLESS_URL"],
        paperless_token=os.environ["PAPERLESS_API_TOKEN"],
    )
    logger.info(
        "extract-pdfs complete in %.2fs: tagged %d message(s) as +paperless",
        time.perf_counter() - started, submitted,
    )


@task(name="push-metrics", log_prints=True)
def push_metrics_task() -> None:
    metrics.push_success_metric()


@flow(name="mail", log_prints=True)
def mail_flow() -> None:
    logger = get_run_logger()
    flow_started = time.perf_counter()
    try:
        with concurrency("mail-pipeline", occupy=1, timeout_seconds=10):
            sync_mail_task()
            index_mail_task()
            extract_pdfs_task()
            push_metrics_task()
        logger.info("mail flow complete in %.2fs", time.perf_counter() - flow_started)
    except TimeoutError:
        logger.info("Skipped — mail pipeline already running")
