#!/usr/bin/env python
"""Prints ping and target-access query stats along with built-in memcached stats."""

import subprocess
from collections import OrderedDict
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

from pymemcache.client.retrying import RetryingClient

from app.common import (
    ISPYB_PING_COUNTER_KEY,
    ISPYB_QUERY_COUNTER_KEY,
    PING_CACHE_KEY,
    PING_COUNTER_KEY,
    QUERY_COUNTER_KEY,
    get_encoded_username_timestamp_key,
    get_memcached_retrying_client,
    valid_encoded_username,
)

_CLIENT: RetryingClient = get_memcached_retrying_client()

# Display built-in memcached stats

_STATS: dict[str, Any] = _CLIENT.stats()
_O_STATS: OrderedDict = OrderedDict(sorted(_STATS.items()))
for key, value in _O_STATS.items():
    stat: str = key.decode("utf-8")
    val: str = value.decode("utf-8") if isinstance(value, bytes) else value
    print(f"{stat}={val}")

print("---")

# Display our own stats (ping/query counts)

PING_STATUS: str | None = _CLIENT.get(PING_CACHE_KEY)
PING_STATUS_STR: str = PING_STATUS or "Unknown"

PING_COUNT: int = _CLIENT.get(PING_COUNTER_KEY)
if PING_COUNT is None:
    PING_COUNT = 0
ISPYB_PING_COUNT: int = _CLIENT.get(ISPYB_PING_COUNTER_KEY)
if ISPYB_PING_COUNT is None:
    ISPYB_PING_COUNT = 0
QUERY_COUNT: int = _CLIENT.get(QUERY_COUNTER_KEY)
if QUERY_COUNT is None:
    QUERY_COUNT = 0
ISPYB_QUERY_COUNT: int = _CLIENT.get(ISPYB_QUERY_COUNTER_KEY)
if ISPYB_QUERY_COUNT is None:
    ISPYB_QUERY_COUNT = 0

PING_REDUCTION_PCENT: int = 0
if PING_COUNT:
    PING_REDUCTION_PCENT = int(
        100.0 * (PING_COUNT - ISPYB_PING_COUNT) / PING_COUNT + 0.5
    )

QUERY_REDUCTION_PCENT: float = 0
if QUERY_COUNT:
    QUERY_REDUCTION_PCENT = int(
        100.0 * (QUERY_COUNT - ISPYB_QUERY_COUNT) / QUERY_COUNT + 0.5
    )

print(f"ping_status='{PING_STATUS_STR}")
print(f"ping_count={ISPYB_PING_COUNT}/{PING_COUNT} (reduction={PING_REDUCTION_PCENT}%)")
print(
    f"query_count={ISPYB_QUERY_COUNT}/{QUERY_COUNT} (reduction={QUERY_REDUCTION_PCENT}%)"
)

# Display users and their target access lists.
# We do this by calling 'memdump' which prints all the keys: -
#   $ memdump -s localhost
#   ispyb-ping
#   query-counter
#   ispyb-query-counter
#   ispyb-ping-counter
#   ping-counter
#   timestamp-ispyb-ping
#
# And we display a summary of the the user info: -
#
# username-key: <KEY> size: <LENGTH OF SET> collected: <UTC DATE/TIME>

print("---")

result = subprocess.run(
    ["memdump", "-s", "localhost"], stdout=subprocess.PIPE, check=False
)
keys = result.stdout.decode("utf-8").split()

# Unquote and sort usernames
usernames: list[str] = []
usernames.extend(unquote(key) for key in keys if valid_encoded_username(key))
usernames.sort()

num_usernames: int = 0  # Number of usernames cached
num_tas: int = 0  # Total number of TAS
max_tas: int = 0  # Largest no. of TAS for any user
for username in usernames:
    encoded_username: str = quote(username)
    collected: datetime = _CLIENT.get(
        get_encoded_username_timestamp_key(encoded_username)
    )
    collected_iso: str = collected.isoformat()
    access: set[str] = _CLIENT.get(encoded_username)
    tas = len(access)
    print(f"username='{username}' #tas={tas} collected={collected_iso}")
    num_usernames += 1
    num_tas += tas
    max_tas = max(max_tas, tas)

if num_usernames:
    print("---")

avg_tas: float = 0 if num_usernames == 0 else num_tas / num_usernames
print(f"total usernames={num_usernames}")
print(f"total tas={num_tas}")
print(f"max tas={max_tas}")
print(f"avg tas={avg_tas}")

# Done

_CLIENT.close()
