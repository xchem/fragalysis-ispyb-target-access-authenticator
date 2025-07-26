"""The entrypoint for the Fragalysis Stack FastAPI ISPyB Target Access Authenticator."""

import json
import logging
import multiprocessing
from datetime import datetime, timedelta, timezone
from logging.config import dictConfig
from typing import Annotated, Any
from urllib.parse import quote

import sshtunnel
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    status,
)
from ispyb.exception import ISPyBConnectionException, ISPyBNoResultException
from pydantic import BaseModel
from pymemcache.client.retrying import RetryingClient

from .common import (
    ISPYB_PING_COUNTER_KEY,
    ISPYB_QUERY_COUNTER_KEY,
    PING_CACHE_KEY,
    PING_CACHE_TIMESTAMP_KEY,
    PING_COUNTER_KEY,
    QUERY_COUNTER_KEY,
    get_encoded_username_timestamp_key,
    get_memcached_retrying_client,
    valid_encoded_username,
)
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

_SEMAPHORE = multiprocessing.Semaphore()

app = FastAPI()

_VERSION_KIND: str = "ISPYB"
_VERSION_NAME: str = "XChem Python FastAPI TAS Authenticator"

# We cache target access strings (obtained from ISPyB) against a key
# based on the URL-encoded value of the user's username.
# We also cache the time (UTC) when the last target access strings were collected.
# This UTC is recorded against the key 'timestamp-{url-encoded-username}'.
# If the timestamp of the cache has expired we try and collect a new set of
# target access strings. if that fails we return the existing cache.
_MAX_USER_CACHE_AGE: timedelta = timedelta(minutes=Config.CACHE_EXPIRY_MINUTES)
_MAX_PING_CACHE_AGE: timedelta = timedelta(seconds=Config.PING_CACHE_EXPIRY_SECONDS)


def _utc_now() -> datetime:
    """Get the current time (UTC)."""
    return datetime.now(timezone.utc)


# Do we have sufficient configuration for an SSH connector?
_SSH_CONNECTOR_CONFIGURED: bool = False
if (
    Config.ISPYB_HOST
    and Config.ISPYB_PORT
    and Config.ISPYB_USER
    and Config.ISPYB_PASSWORD
    and Config.SSH_HOST
    and Config.SSH_USER
    and (Config.SSH_PRIVATE_KEY_FILENAME or Config.SSH_PASSWORD)
):
    # Create a connector
    _SSH_CONNECTOR_CONFIGURED = True
    _LOGGER.info("I have sufficient configuration to establish an SSH connection")
else:
    _LOGGER.warning("Insufficient configuration to establish an SSH connection")

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


class TargetAccessGetPingResponse(BaseModel):
    """/ping/ GET response."""

    # Ping OK or FAILURE
    ping: str


class TargetAccessGetUserTasResponse(BaseModel):
    """/target-access/{username}/ GET response."""

    # Number of Target Access Strings in the response
    count: int
    # Possibly empty set of Target Access strings
    target_access: set[str]


def _get_connector() -> SSHConnector | None:
    """Tries to create an SSHConnector(), which may fail."""
    conn: SSHConnector | None = None
    if _SSH_CONNECTOR_CONFIGURED:
        _LOGGER.debug("Creating SSHConnector() for '%s'..", Config.SSH_HOST)
        try:
            conn = SSHConnector()
        except ISPyBConnectionException:
            # The ISPyB connection failed.
            # Nothing else to do here, metrics are already updated
            _LOGGER.warning("ISPyB connection failure")
        except sshtunnel.BaseSSHTunnelForwarderError:
            _LOGGER.warning("Failed to establish a connector")
    else:
        _LOGGER.debug("Insufficient configuration to create a connector")

    return conn


def _get_tas_from_remote_ispyb(username: str) -> set[str] | None:
    """Gets the user's proposal. It returns None on error, an empty set if
    there are no proposals or a set of proposals.
    """
    assert username

    ssh_connector: SSHConnector | None = _get_connector()
    if not ssh_connector:
        _LOGGER.warning("No SSH connector for user '%s'", username)
        return None

    prop_id_set: set[str] = set()
    rs: list[dict[str, Any]] | None = None
    try:
        rs = ssh_connector.core.retrieve_sessions_for_person_login(username)
    except ISPyBNoResultException:
        _LOGGER.debug("ISPyBNoResultException for user '%s'", username)
        rs = []
    # Request done, always stop the server
    if ssh_connector.server:
        ssh_connector.server.stop()

    # Anything to process?
    if rs is None:
        return None
    if not rs:
        _LOGGER.debug("No results for user '%s'", username)
        return prop_id_set

    # Typically you'll find the following fields in each item
    # in the rs response: -
    #
    #    'id': 0000000,
    #    'proposalId': 00000,
    #    'startDate': datetime.datetime(2022, 12, 1, 15, 56, 30)
    #    'endDate': datetime.datetime(2022, 12, 3, 18, 34, 9)
    #    'beamline': 'i00-0'
    #    'proposalCode': 'lb'
    #    'proposalNumber': '12345'
    #    'sessionNumber': 1
    #    'comments': None
    #    'personRoleOnSession': 'Data Access'
    #    'personRemoteOnSession': 1
    #
    # Iterate through the response and return the 'proposalNumber' (proposals)
    # and one with the 'proposalNumber' and 'sessionNumber' (visits), each
    # prefixed by the `proposalCode` (if present).
    #
    # Codes are expected to consist of 2 letters.
    # Typically: lb, mx, nt, nr, bi but the codes we support
    # are defined in Config.TAS_CODES_SET.
    #
    # These strings should correspond to a title value in a Project record.
    # and should get this sort of set: -
    #
    # ["lb12345", "lb12345-1"]
    #              --      -
    #              | ----- |
    #           Code   |   Session
    #               Proposal
    for record in rs:
        if "proposalCode" in record and record["proposalCode"] in Config.TAS_CODES_SET:
            pc_str = f'{record["proposalCode"]}'
            pn_str = f'{record["proposalNumber"]}'
            sn_str = f'{record["sessionNumber"]}'
            proposal_str = f"{pc_str}{pn_str}"
            proposal_visit_str = f"{proposal_str}-{sn_str}"
            prop_id_set.update([proposal_str, proposal_visit_str])

    # Display the collected results for the user.
    # These will be cached.
    count = len(prop_id_set)
    _LOGGER.debug(
        "%s proposals from %s records for '%s': %s",
        count,
        len(rs),
        username,
        prop_id_set,
    )
    return prop_id_set


def _try_memcached_client_get(client: RetryingClient, key: str) -> Any:
    """Common memcached get() logic, handling expected exceptions."""
    response: Any = None
    err: str | None = None
    err_msg: str | None = None

    try:
        response = client.get(key)
    except AssertionError as a_err:
        err = a_err.__class__.__name__
        err_msg = str(a_err)
    except KeyError as k_err:
        err = k_err.__class__.__name__
        err_msg = str(k_err)
    except TimeoutError as t_err:
        err = t_err.__class__.__name__
        err_msg = str(t_err)
    except OSError as o_err:
        err = o_err.__class__.__name__
        err_msg = str(o_err)

    if err:
        _LOGGER.warning("Cache GET %s with %s (%s)", err, key, err_msg)

    return response


# Inject some mock data for "dave lister"?
if Config.ENABLE_DAVE_LISTER:
    _DUMMY_USER: str = quote("dave lister")
    dummy_user_client: RetryingClient = get_memcached_retrying_client()
    assert dummy_user_client
    dummy_user_client.set(_DUMMY_USER, set(["sb99999-9"]))
    dummy_user_client.set(get_encoded_username_timestamp_key(_DUMMY_USER), _utc_now())
    dummy_user_client.close()


# Clear counter/stats values
# We count the number of ping calls and query calls
counter_client: RetryingClient = get_memcached_retrying_client()
assert counter_client
counter_client.set(PING_COUNTER_KEY, 0)
counter_client.set(ISPYB_PING_COUNTER_KEY, 0)
counter_client.set(QUERY_COUNTER_KEY, 0)
counter_client.set(ISPYB_QUERY_COUNTER_KEY, 0)
counter_client.close()


# Endpoints (in-cluster) for the ISPyP Authenticator -----------------------------------


@app.get("/version/", status_code=status.HTTP_200_OK)
def get_taa_version() -> TargetAccessGetVersionResponse:
    """Returns our version information"""
    return TargetAccessGetVersionResponse(
        kind=_VERSION_KIND,
        name=_VERSION_NAME,
        version=_VERSION,
    )


@app.get("/ping/", status_code=status.HTTP_200_OK)
def ping():
    """Returns 'OK' if we can communicate with the underlying ISPyB service
    (i.e. create a connector). Anything other than 'OK' indicates a problem.
    We Throttle /ping requests by only querying the underlying service
    if there's no cached ping result or it's too old.
    """
    with _SEMAPHORE:
        client: RetryingClient = get_memcached_retrying_client()
        assert client
        client.incr(PING_COUNTER_KEY, 1)

        # Current ping state (in the cache)
        # we do this so we can log changes.
        pre_ping_status: str | None = _try_memcached_client_get(client, PING_CACHE_KEY)

        ping_cache_timestamp: datetime | None = _try_memcached_client_get(
            client, PING_CACHE_TIMESTAMP_KEY
        )

        status_str: str = "NOT OK"
        utc_now: datetime = _utc_now()
        if (
            pre_ping_status is None
            or not ping_cache_timestamp
            or utc_now - ping_cache_timestamp > _MAX_PING_CACHE_AGE
        ):
            _LOGGER.debug("ping cache value is too old - refreshing...")
            if ssh_connector := _get_connector():
                assert ssh_connector.server
                ssh_connector.server.stop()
                status_str = "OK"
            client.incr(ISPYB_PING_COUNTER_KEY, 1)
            client.set(PING_CACHE_KEY, status_str)
            client.set(PING_CACHE_TIMESTAMP_KEY, utc_now)
        else:
            # Ping has not expired and should be set to something...
            status_str = pre_ping_status

        client.close()

        if status_str != pre_ping_status:
            _LOGGER.info("New ISPyB PING status [%s->%s]", pre_ping_status, status_str)

    return TargetAccessGetPingResponse(ping=status_str)


@app.get("/target-access/{username}", status_code=status.HTTP_200_OK)
def get_taa_user_tas(
    username: str,
    x_taaquerykey: Annotated[str | None, Header()] = None,
):
    """Returns the list of target access strings for a user.
    The user must provide a valid 'query key' - the one we've been
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
    # memcached has a key size limit of 250 characters.
    encoded_username: str = quote(username)
    if len(encoded_username) > 250:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encoded username exceeds 250 characters",
        )

    if not valid_encoded_username(encoded_username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username cannot be '{username}'",
        )

    with _SEMAPHORE:
        client: RetryingClient = get_memcached_retrying_client()
        assert client
        client.incr(QUERY_COUNTER_KEY, 1)

        # If the user's cache record is not present (may have been ejected by memcached),
        # too old, or there is no cache timestamp then refresh the cache
        # using the underlying ISPyB DB.
        existing_cache: set[str] | None = _try_memcached_client_get(
            client, encoded_username
        )
        user_timestamp_key: str = get_encoded_username_timestamp_key(encoded_username)
        user_cache_timestamp: datetime = _try_memcached_client_get(
            client, user_timestamp_key
        )
        utc_now: datetime = _utc_now()
        user_cache: set[str] = set()
        if (
            existing_cache is None
            or not user_cache_timestamp
            or utc_now - user_cache_timestamp > _MAX_USER_CACHE_AGE
        ):
            _LOGGER.debug("Attempting to refresh the cache for '%s'...", username)
            remote_tas_set: set[str] | None = _get_tas_from_remote_ispyb(
                username=username
            )
            if remote_tas_set is not None:
                # Got something (may be empty).
                # An empty list is considered successful - it means the user is known
                # but does not have access to any proposals/visits.
                user_cache = remote_tas_set
            else:
                _LOGGER.warning("Failed to get TAS set for '%s'", username)
            # Reset the user's cache timestamp regardless of success.
            # We'll try this user again at the next expiry.
            _LOGGER.info(
                "Cache replacement for '%s' (size=%d)", username, len(user_cache)
            )
            client.incr(ISPYB_QUERY_COUNTER_KEY, 1)
            client.set(encoded_username, user_cache)
            client.set(user_timestamp_key, utc_now)
        else:
            # Cache has not expired and should be set to something...
            user_cache = existing_cache

        client.close()

        count: int = len(user_cache)
        record: str = "record" if count == 1 else "records"
        _LOGGER.debug("Returning %s %s for '%s'", count, record, username)

    return TargetAccessGetUserTasResponse(
        count=count,
        target_access=user_cache,
    )
