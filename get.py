#!/usr/bin/env python
"""Gets the cache for a given user."""

import os
import sys
from typing import NoReturn
from urllib.parse import quote

import requests

from app.common import (
    valid_encoded_username,
)


def error(msg: str) -> NoReturn:
    print(f"ERROR: {msg}")
    print('Usage: get.py [username|"user name"]')
    sys.exit(1)


if len(sys.argv) != 2:
    error("Missing username")

_USERNAME: str = sys.argv[1]
_ENCODED_USERNAME: str = quote(_USERNAME)
_QUERY_KEY: str = os.environ["TAA_QUERY_KEY"]

if not valid_encoded_username(_ENCODED_USERNAME):
    error(f'"{_USERNAME}" is not a valid username')

# Trigger a local request (using the API)
# to get the Target Access strings for the user
resp: requests.Response = requests.get(
    f"http://auth/target-access/{_ENCODED_USERNAME}",
    headers={"X-TAAQueryKey": _QUERY_KEY},
    timeout=4,
)
if resp.status_code == 200:
    print(resp.text)
else:
    error(f"Failed get request ({resp.status_code}) '{resp.text}")
