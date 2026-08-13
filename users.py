#!/usr/bin/env python
"""Prints the raw ISPyB response for the members of a given target access string.

Unlike get.py this does not use the local API - it calls the ISPyB
'retrieve_persons_for_session' stored procedure directly and prints whatever
comes back, which is the quickest way to see what the database is really
saying. A failure (at the time of writing our account is not permitted to
execute the procedure) is printed rather than raised - the '/users/{tas}'
endpoint turns the same failure into an empty set of users.
"""

import pprint
import sys
from typing import Any, NoReturn

import ispyb
import sshtunnel

from app.common import split_tas
from app.remote_ispyb_connector import SSHConnector


def error(msg: str) -> NoReturn:
    """Prints an error and usage, and then gives up."""
    print(f"ERROR: {msg}")
    print("Usage: users.py [target-access-string]")
    sys.exit(1)


def call(connector: SSHConnector, name: str, *args: str) -> None:
    """Calls one of the 'core' retrieval methods, printing the raw response."""
    print(f"--- {name}{args}")
    try:
        response: list[dict[str, Any]] = getattr(connector.core, name)(*args)
    except ispyb.NoResult:
        # The connector raises this for an empty result-set.
        # We cannot tell "no such proposal" from "no members" here.
        print("ispyb.NoResult (empty result-set)")
        return
    except Exception as ex:  # pylint: disable=broad-exception-caught
        # Typically a missing stored procedure, which is what we are trying
        # to find out, so report it rather than letting it escape.
        print(f"{ex.__class__.__name__}: {ex}")
        return

    print(f"{len(response)} record(s)")
    pprint.pprint(response)
    if response:
        print("Keys:")
        pprint.pprint(sorted(response[0].keys()))


if len(sys.argv) != 2:
    error("Missing target access string")

_TAS: str = sys.argv[1]
_TAS_PARTS: tuple[str, str, str] | None = split_tas(_TAS)
if not _TAS_PARTS:
    error(
        f'"{_TAS}" is not a target access string (expected something like "lb12345-1")'
    )

_CODE, _PROPOSAL_NUMBER, _VISIT_NUMBER = _TAS_PARTS
print(f"       TAS: '{_TAS}'")
print(f"      Code: '{_CODE}'")
print(f"  Proposal: '{_PROPOSAL_NUMBER}'")
print(f"     Visit: '{_VISIT_NUMBER}'")

# Connect to ISPyB.
# The connector is created (and stopped) here, just like the app does
# for each request.
_CONNECTOR: SSHConnector | None = None
try:
    _CONNECTOR = SSHConnector()
except ispyb.ConnectionError:
    error("ISPyB connection failure (are the ISPyB credentials correct?)")
except sshtunnel.BaseSSHTunnelForwarderError:
    error("Failed to establish an SSH tunnel")
except ValueError as v_err:
    # sshtunnel raises this when it has neither a password nor a key file,
    # i.e. the container has not been given any TAA_SSH_* configuration.
    error(f"No SSH credentials - is this container configured for ISPyB? ({v_err})")

assert _CONNECTOR
try:
    call(
        _CONNECTOR,
        "retrieve_persons_for_session",
        _CODE,
        _PROPOSAL_NUMBER,
        _VISIT_NUMBER,
    )
finally:
    if _CONNECTOR.server:
        _CONNECTOR.server.stop()
