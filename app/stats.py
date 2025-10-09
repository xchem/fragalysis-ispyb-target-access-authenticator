#!/usr/bin/env python
"""Collects ping and target-access query stats along with built-in memcached stats."""

import subprocess
from collections import OrderedDict
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

import humanize
from pymemcache.client.retrying import RetryingClient

from app.common import (
    ISPYB_PING_COUNTER_KEY,
    ISPYB_QUERY_COUNTER_KEY,
    PING_CACHE_KEY,
    PING_CACHE_TIMESTAMP_KEY,
    PING_COUNTER_KEY,
    PING_STATUS_CHANGE_TIMESTAMP_KEY,
    QUERY_COUNTER_KEY,
    get_encoded_username_timestamp_key,
    get_memcached_retrying_client,
    utc_now,
    valid_encoded_username,
)
from app.config import Config


def get_stats() -> dict[str, Any]:
    """Returns a detailed collection of stats as a dictionary of keys and values."""

    stats_response: dict[str, Any] = {}

    client: RetryingClient = get_memcached_retrying_client()

    # Collect built-in memcached stats

    memcached_stats: dict[str, Any] = {}
    stats: dict[str, Any] = client.stats()
    o_stats: OrderedDict = OrderedDict(sorted(stats.items()))
    for key, value in o_stats.items():
        stat: str = key.decode("utf-8")
        val: str = value.decode("utf-8") if isinstance(value, bytes) else value
        memcached_stats[stat] = val
    stats_response["memcached"] = memcached_stats

    # Collect our own stats (ping/query counts)

    ping_status: str | None = client.get(PING_CACHE_KEY)
    ping_status_str: str = ping_status or "Unknown"

    ping_count: int = client.get(PING_COUNTER_KEY)
    if ping_count is None:
        ping_count = 0
    ispyb_ping_count: int = client.get(ISPYB_PING_COUNTER_KEY)
    if ispyb_ping_count is None:
        ispyb_ping_count = 0
    query_count: int = client.get(QUERY_COUNTER_KEY)
    if query_count is None:
        query_count = 0
    ispyb_query_count: int = client.get(ISPYB_QUERY_COUNTER_KEY)
    if ispyb_query_count is None:
        ispyb_query_count = 0

    now: datetime = utc_now()

    ping_status_change_timestamp: datetime | None = client.get(
        PING_STATUS_CHANGE_TIMESTAMP_KEY
    )
    ping_status_change_timestamp_str: str = (
        ping_status_change_timestamp.isoformat()
        if ping_status_change_timestamp
        else "No change yet"
    )
    ping_status_change_age_str: str = "Meaningless"
    if isinstance(ping_status_change_timestamp, datetime):
        ping_status_change_age_str = humanize.naturaldelta(
            now - ping_status_change_timestamp
        )

    ping_timestamp: datetime | None = client.get(PING_CACHE_TIMESTAMP_KEY)
    ping_timestamp_str: str = (
        ping_timestamp.isoformat() if ping_timestamp else "No ping yet"
    )
    ping_age_str: str = "Meaningless"
    if isinstance(ping_timestamp, datetime):
        ping_age_str = humanize.naturaldelta(now - ping_timestamp)

    ping_reduction_pcent: int = 0
    if ping_count:
        ping_reduction_pcent = int(
            100.0 * (ping_count - ispyb_ping_count) / ping_count + 0.5
        )

    query_reduction_pcent: float = 0
    if query_count:
        query_reduction_pcent = int(
            100.0 * (query_count - ispyb_query_count) / query_count + 0.5
        )

    stats_response["ping"] = {
        "status": ping_status_str,
        "timestamp": ping_timestamp_str,
        "age": ping_age_str,
        "status_change_timestamp": ping_status_change_timestamp_str,
        "status_change_age": ping_status_change_age_str,
        "ping_count": f"{ispyb_ping_count}/{ping_count}",
        "ping_reduction": f"{ping_reduction_pcent}%",
        "query_count": f"{ispyb_query_count}/{query_count}",
        "query_reduction": f"{query_reduction_pcent}%",
    }

    # Collect users and their target access lists.
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

    result = subprocess.run(
        ["memdump", "-s", "localhost"], stdout=subprocess.PIPE, check=False
    )
    keys = result.stdout.decode("utf-8").split()

    # Unquote and sort usernames
    usernames: list[str] = []
    usernames.extend(unquote(key) for key in keys if valid_encoded_username(key))
    usernames.sort()

    user_stats: list[dict[str, Any]] = []
    num_usernames: int = 0  # Number of usernames cached
    num_tas: int = 0  # Total number of TAS
    max_tas: int = 0  # Largest no. of TAS for any user
    for username in usernames:
        encoded_username: str = quote(username)
        collected: datetime = client.get(
            get_encoded_username_timestamp_key(encoded_username)
        )
        collected_iso: str = collected.isoformat()
        access: set[str] = client.get(encoded_username)
        tas = len(access)
        user_stats.append(
            {"username": username, "tas_count": tas, "collected": collected_iso}
        )
        num_usernames += 1
        num_tas += tas
        max_tas = max(max_tas, tas)

    if num_usernames:
        print("---")

    avg_tas: int = 0 if num_usernames == 0 else int(0.5 + num_tas / num_usernames)
    stats_response["users"] = {
        "total_usernames": num_usernames,
        "total_tas_count": num_tas,
        "max_tas_count": max_tas,
        "avg_tas_count": avg_tas,
        "user_stats": user_stats,
    }

    stats_response["code_set"] = list(Config.TAS_CODES_SET)

    # Done

    client.close()

    return stats_response
