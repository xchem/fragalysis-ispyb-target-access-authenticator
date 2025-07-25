#!/usr/bin/env python
"""Prints ping and target-access query stats."""
from pymemcache.client.retrying import RetryingClient

from app.common import (
    ISPYB_PING_COUNTER_KEY,
    ISPYB_QUERY_COUNTER_KEY,
    PING_COUNTER_KEY,
    QUERY_COUNTER_KEY,
    get_memcached_retrying_client,
)

_CLIENT: RetryingClient = get_memcached_retrying_client()
PING_COUNT: int = _CLIENT.get(PING_COUNTER_KEY)
ISPYB_PING_COUNT: int = _CLIENT.get(ISPYB_PING_COUNTER_KEY)
QUERY_COUNT: int = _CLIENT.get(QUERY_COUNTER_KEY)
ISPYB_QUERY_COUNT: int = _CLIENT.get(ISPYB_QUERY_COUNTER_KEY)
_CLIENT.close()

print(
    f"ping_count={ISPYB_PING_COUNT}/{PING_COUNT} query_count={ISPYB_QUERY_COUNT}/{QUERY_COUNT}"
)
