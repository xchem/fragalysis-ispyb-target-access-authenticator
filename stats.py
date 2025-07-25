#!/usr/bin/env python
import os

from pymemcache.client.base import Client
from pymemcache.client.retrying import RetryingClient
from pymemcache.exceptions import MemcacheUnexpectedCloseError

_PING_COUNTER_KEY: str = "ping-counter"
_ISPYB_PING_COUNTER_KEY: str = "ispyb-ping-counter"
_QUERY_COUNTER_KEY: str = "query-counter"
_ISPYB_QUERY_COUNTER_KEY: str = "ispyb-query-counter"

_BASE_CLIENT: Client = Client(
    os.getenv("TAA_MEMCACHED_LOCATION", "localhost"),
    connect_timeout=4,
    timeout=0.5,
    ignore_exc=True,
)
_CLIENT: RetryingClient = RetryingClient(
    _BASE_CLIENT,
    attempts=5,
    retry_delay=0.5,
    retry_for=[MemcacheUnexpectedCloseError],
)

ping_count: int = _CLIENT.get(_PING_COUNTER_KEY)
ispyb_ping_count: int = _CLIENT.get(_ISPYB_PING_COUNTER_KEY)
query_count: int = _CLIENT.get(_QUERY_COUNTER_KEY)
ispyb_query_count: int = _CLIENT.get(_ISPYB_QUERY_COUNTER_KEY)
_CLIENT.close()

print(
    f"ping_count={ispyb_ping_count}/{ping_count} query_count={ispyb_query_count}/{query_count}"
)
