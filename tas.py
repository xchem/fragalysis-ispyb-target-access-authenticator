#!/usr/bin/env python
"""Prints the cached target-access strings for a given user."""

import os
import pprint
import sys
from datetime import datetime
from typing import NoReturn
from urllib.parse import quote

from pymemcache.client.retrying import RetryingClient

from app.common import (
    get_encoded_username_timestamp_key,
    get_memcached_retrying_client,
    valid_encoded_username,
)


def error(msg: str) -> NoReturn:
    print(f"ERROR: {msg}")
    print('Usage: tas.py [username|"user name"]')
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
_TAS: set[str] = _CLIENT.get(_ENCODED_USERNAME) or set()
_COLLECTED: datetime | None = _CLIENT.get(
    get_encoded_username_timestamp_key(_ENCODED_USERNAME)
)
_CLIENT.close()

_COLLECTED_STR: str = _COLLECTED.isoformat() if _COLLECTED else "Nothing collected"

print(f"  Username: '{_USERNAME}' ({_ENCODED_USERNAME})")
print(f" Collected: {_COLLECTED_STR}")
print(f"No. of TAS: {len(_TAS)}")
if _TAS:
    print("   TAS Set:")
    _TERMINAL_WIDTH: int = os.get_terminal_size()[0]
    pprint.pprint(_TAS, width=_TERMINAL_WIDTH, compact=True)
