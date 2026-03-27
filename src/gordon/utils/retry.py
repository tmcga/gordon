"""Retry decorators built on tenacity for common Gordon patterns."""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from gordon.core.errors import BrokerError

# ---------------------------------------------------------------------------
# Network retry: ConnectionError, TimeoutError, httpx.HTTPError
# 3 attempts, exponential backoff starting at 0.5s, max 10s
# ---------------------------------------------------------------------------
retry_network = retry(
    retry=retry_if_exception_type((ConnectionError, TimeoutError, httpx.HTTPError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=10),
    reraise=True,
)

# ---------------------------------------------------------------------------
# Broker retry: BrokerError
# 5 attempts, exponential backoff starting at 1s, max 30s
# ---------------------------------------------------------------------------
retry_broker = retry(
    retry=retry_if_exception_type(BrokerError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=30),
    reraise=True,
)
