"""Pushgateway metric reporter."""

from __future__ import annotations

import logging
import os
import time

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

logger = logging.getLogger(__name__)


def push_success_metric() -> None:
    """Push the `mail_pipeline_last_success_timestamp` gauge to Pushgateway.

    No-op when `PUSHGATEWAY_URL` is unset.
    """
    url = os.environ.get("PUSHGATEWAY_URL", "")
    if not url:
        return

    registry = CollectorRegistry()
    gauge = Gauge(
        "mail_pipeline_last_success_timestamp",
        "Unix timestamp of the last successful mail-pipeline run",
        registry=registry,
    )
    gauge.set(time.time())

    try:
        push_to_gateway(url, job="mail-pipeline", registry=registry, timeout=10)
    except Exception as exc:
        logger.warning("Pushgateway push failed: %s", exc)
