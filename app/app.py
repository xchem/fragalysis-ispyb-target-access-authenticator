"""The entrypoint for the Fragalysis Stack FastAPI ISPyB Target Access Authenticator."""

import json
import logging
from datetime import datetime, timedelta, timezone
from logging.config import dictConfig
from typing import Annotated, Any
from urllib.parse import quote

from dateutil.parser import parse
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

from .config import Config
from .remote_ispyb_connector import SSHConnector

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
    if isinstance(value, str):
        return (value, 1)
    if isinstance(value, datetime):
        return (str(value), 2)
    return (json.dumps(value), 3)


def _json_deserialiser(key, value, flags):
    del key
    if flags == 1:
        return value
    if flags == 2:
        return parse(value)
    if flags == 3:
        return json.loads(value)
    # How did we get here?
    assert False


# We cache target access strings (obtained from ISPyB) against a key
# based on the URL-encoded value of the user's username.
# We also cache the time (UTC) when the last target access strings were collected.
# This UTC is recorded against the key 'timestamp-{url-encoded-username}'.
# If the timestamp of the cache has expired we try and collect a new set of
# target access strings. if that fails we return the existing cache.

_TIMESTAMP_KEY_PREFIX: str = "timestamp-"
_MAX_USER_CACHE_AGE: timedelta = timedelta(minutes=Config.CACHE_EXPIRY_MINUTES)

# The location is either a host ("localhost") or host and port ("localhost:1234").
# If the port is not the expected default of 11211 is assumed.
_MEMCACHED_KEEPALIVE: KeepaliveOpts = KeepaliveOpts(idle=35, intvl=8, cnt=5)
_MEMCACHED_BASE_CLIENT: Client = Client(
    Config.MEMCACHED_LOCATION,
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Inject some mock data for "dave lister".
# Test data that expires after the configured cache period.
_DUMMY_USER: str = "dave%20lister"
_MEMCACHED_CLIENT.set(_DUMMY_USER, ["sb-99999"])
_MEMCACHED_CLIENT.set(f"{_TIMESTAMP_KEY_PREFIX}{_DUMMY_USER}", _utc_now())

# Do we have a connector configured?
# Yes if: -
# - Config.ISPYB_HOST
_SSH_CONNECTOR: SSHConnector | None = None
if Config.ISPYB_HOST:
    # Other ISPyB variables are required...
    assert Config.ISPYB_PORT
    assert Config.ISPYB_USER
    assert Config.ISPYB_PASSWORD
    # And SSH variables...
    assert Config.SSH_HOST
    assert Config.SSH_USER
    assert Config.SSH_PASSWORD or Config.SSH_PRIVATE_KEY_FILENAME
    # Create a connector
    _SSH_CONNECTOR = SSHConnector()

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
    # We can only continue if the correct query key has been provided.
    if Config.QUERY_KEY and x_taaquerykey != Config.QUERY_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid/missing X_TAAQueryKey",
        )
    _LOGGER.debug("Request for '%s'", username)

    # FastAPI decodes url-encoded strings and memcached keys cannot contain spaces
    # so we need to re-encode the username for cache lookup.
    encoded_username: str = quote(username)

    # Get cached user data and any related timestamp.
    user_timestamp_key: str = f"{_TIMESTAMP_KEY_PREFIX}{encoded_username}"
    user_cache: list[str] | None = _MEMCACHED_CLIENT.get(encoded_username)
    user_cache_timestamp: datetime | None = _MEMCACHED_CLIENT.get(user_timestamp_key)

    # If the user's cache record is too (or there is no cache timestamp)
    # old then refresh the cache from the ISPyB DB.
    utc_now: datetime = _utc_now()
    if not user_cache_timestamp or utc_now - user_cache_timestamp > _MAX_USER_CACHE_AGE:
        print("Would fetch new data now...")
        # Reset the user's cache timestamp regardless of success.
        # We'll try this user again at the next expiry.
        _MEMCACHED_CLIENT.set(user_timestamp_key, utc_now)

    tas_list: list[str] = user_cache if user_cache is not None else []
    count: int = len(tas_list)
    _LOGGER.debug("Returning %s for '%s'", count, username)
    return TargetAccessGetUserTasResponse(
        count=count,
        target_access=tas_list,
    )
