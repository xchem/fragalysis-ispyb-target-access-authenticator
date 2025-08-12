#!/usr/bin/env python
"""Clears the cache for a given user."""

import sys
from typing import NoReturn
from urllib.parse import quote

from pymemcache.client.retrying import RetryingClient

from app.common import (
    get_memcached_retrying_client,
    valid_encoded_username,
)


def error(msg: str) -> NoReturn:
    print(f"ERROR: {msg}")
    print('Usage: clear.py [username|"user name"]')
    sys.exit(1)


if len(sys.argv) != 2:
    error("Missing username")

_USERNAME: str = sys.argv[1]
_ENCODED_USERNAME: str = quote(_USERNAME)

if not valid_encoded_username(_ENCODED_USERNAME):
    error(f'"{_USERNAME}" is not a valid username')

# Get the Target Access strings for the user
# and the time they were collected
_CLIENT: RetryingClient = get_memcached_retrying_client()
_ = _CLIENT.delete(_ENCODED_USERNAME)
_CLIENT.close()
