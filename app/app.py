"""The entrypoint for the Fragalysis Stack FastAPI ISPyB Target Access Authenticator."""

import json
import logging
import os
from logging.config import dictConfig
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    status,
)
from pydantic import BaseModel
from pymemcache.client.base import Client, KeepaliveOpts
from pymemcache.client.retrying import RetryingClient
from pymemcache.exceptions import MemcacheUnexpectedCloseError

# Configure logging
print("Configuring logging...")
_LOGGING_CONFIG: dict[str, Any] = {}
with open("logging.config", "r", encoding="utf8") as stream:
    try:
        _LOGGING_CONFIG = json.loads(stream.read())
    except json.decoder.JSONDecodeError as exc:
        print(exc)
dictConfig(_LOGGING_CONFIG)
print("Configured logging.")

_LOGGER = logging.getLogger(__name__)

app = FastAPI()

# Configure memcached.


# We use custom serialisers to convert our list of strings
# to/from a string (which is the memcached native value type).
# Memcached value size if limited to 1MB - about 90_000 TAS strings?
def _json_serialiser(key, value):
    del key
    return (value, 1) if isinstance(value, str) else (json.dumps(value), 2)


def _json_deserialiser(key, value, flags):
    del key
    if flags == 1:
        return value
    if flags == 2:
        return json.loads(value)
    # How did we get here?
    assert False


# Our Query Key?
# One that must be provided by clients (via the header) when querying.
_QUERY_KEY: str = os.getenv("TAA_QUERY_KEY", "")
assert _QUERY_KEY

# The location is either a host ("localhost") or host and port ("localhost:1234").
# If the port is not the expected default of 11211 is assumed.
_MEMCACHED_LOCATION: str = os.getenv("TAA_MEMCACHED_LOCATION", "localhost")
_MEMCACHED_KEEPALIVE: KeepaliveOpts = KeepaliveOpts(idle=35, intvl=8, cnt=5)
_MEMCACHED_BASE_CLIENT: Client = Client(
    _MEMCACHED_LOCATION,
    connect_timeout=4,
    encoding="utf-8",
    timeout=0.5,
    socket_keepalive=_MEMCACHED_KEEPALIVE,
    serializer=_json_serialiser,
    deserializer=_json_deserialiser,
)
_MEMCACHED_CLIENT: RetryingClient = RetryingClient(
    _MEMCACHED_BASE_CLIENT,
    attempts=3,
    retry_delay=0.01,
    retry_for=[MemcacheUnexpectedCloseError],
)

# Some mock data
_MEMCACHED_CLIENT.set("dave%20lister", ["sb-99999"])

# Get our version (from the 'VERSION' file)
with open("VERSION", "r", encoding="utf-8") as version_file:
    _VERSION: str = version_file.read().strip()


class TargetAccessGetVersionResponse(BaseModel):
    """/version/ GET response."""

    # The Kind of Authenticator (i.e. "ISPYB")
    kind: str
    # Our name (ours is 'Python FastAPI')
    name: str
    # Our version number
    version: str


class TargetAccessGetUserTasResponse(BaseModel):
    """/target-access/{username}/ GET response."""

    # Number of Target Access Strings in the response
    count: int
    # Possibly empty list of Target Access strings
    target_access: list[str]


# Endpoints for the 'public-facing' event-stream web-socket API ------------------------


@app.get("/version/", status_code=status.HTTP_200_OK)
def get_taa_version() -> TargetAccessGetVersionResponse:
    """Returns our version information"""
    return TargetAccessGetVersionResponse(
        kind="ISPYB",
        name="Python FastAPI",
        version=_VERSION,
    )


@app.get("/target-access/{username}", status_code=status.HTTP_200_OK)
def get_taa_user_tas(
    username: str,
    x_taaquerykey: Annotated[str | None, Header()] = None,
):
    """Returns the list of target access strings for a user.
    the user must provide a valid 'query key' - the one we've been
    configured with.
    """
    # Must not continue unless the correct query key has been provided.
    if x_taaquerykey != _QUERY_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid/missing X_TAAQueryKey",
        )

    # FastAPI decodes url-encoded strings and memcached keys cannot contain spaces
    # so we need to re-encode the username for cache lookup.
    encoded_username: str = quote(username)
    cache = _MEMCACHED_CLIENT.get(encoded_username)
    tas_list: list[str] = cache if cache is not None else []

    count: int = len(tas_list)
    _LOGGER.info("Request for '%s' (count=%s)", username, count)

    return TargetAccessGetUserTasResponse(
        count=count,
        target_access=tas_list,
    )
