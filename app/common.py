from datetime import datetime

from dateutil.parser import parse
from pymemcache.client.base import Client
from pymemcache.client.retrying import RetryingClient
from pymemcache.exceptions import MemcacheUnexpectedCloseError

from .config import Config

# Counters (stats)
PING_CACHE_KEY: str = "ispyb-ping"
PING_COUNTER_KEY: str = "ping-counter"
ISPYB_PING_COUNTER_KEY: str = "ispyb-ping-counter"
QUERY_COUNTER_KEY: str = "query-counter"
ISPYB_QUERY_COUNTER_KEY: str = "ispyb-query-counter"

TIMESTAMP_KEY_PREFIX: str = "timestamp-"

PING_CACHE_TIMESTAMP_KEY: str = f"{TIMESTAMP_KEY_PREFIX}{PING_CACHE_KEY}"

# List of invalid (reserved) usernames
INVALID_USERNAMES: set[str] = {
    ISPYB_PING_COUNTER_KEY,
    ISPYB_QUERY_COUNTER_KEY,
    PING_CACHE_KEY,
    PING_COUNTER_KEY,
    QUERY_COUNTER_KEY,
}


# We use custom serializers to convert our objects
# to/from a string (which is the memcached native value type).
# Memcached value size if limited to 1MB - about 90_000 TAS strings?
class TaSerde:
    def serialize(self, key, value):
        del key
        if isinstance(value, str):
            return (value, 1)
        if isinstance(value, int):
            return (str(value), 2)
        if isinstance(value, datetime):
            return (str(value), 3)
        return (repr(value), 4)

    def deserialize(self, key, value, flags):
        del key
        if flags == 1:
            # Strings are stored as bytes,
            # so we convert back to string
            return value.decode("utf-8")
        if flags == 2:
            return int(value)
        if flags == 3:
            return parse(value)
        if flags == 4:
            return eval(value)  # pylint: disable=eval-used
        # How did we get here?
        assert False


_TA_SERDE: TaSerde = TaSerde()


def get_encoded_username_timestamp_key(encoded_username: str) -> str:
    return f"{TIMESTAMP_KEY_PREFIX}{encoded_username}"


def valid_encoded_username(encoded_username: str) -> bool:
    if encoded_username in INVALID_USERNAMES:
        return False
    return not encoded_username.startswith(TIMESTAMP_KEY_PREFIX)


def get_memcached_retrying_client() -> RetryingClient:
    # The location is either a host ("localhost") or host and port ("localhost:1234").
    # If the port is not the expected default of 11211 is assumed.
    base_client: Client = Client(
        Config.MEMCACHED_LOCATION,
        connect_timeout=4,
        timeout=0.5,
        ignore_exc=True,
        serde=_TA_SERDE,
    )
    return RetryingClient(
        base_client,
        attempts=5,
        retry_delay=0.5,
        retry_for=[MemcacheUnexpectedCloseError],
    )
