"""Tests for the ISPyB connector's use of the 'ispyb' package API.

These do not need a database - they assert that we are using the API that the
installed version of the 'ispyb' package actually provides.
"""

import inspect
import time

import ispyb
import pytest
from ispyb.sp.core import Core

from app.remote_ispyb_connector import SSHConnector


def _unconnected_connector(last_activity_ts: float | None) -> SSHConnector:
    """An SSHConnector that has not been through __init__ (so no SSH tunnel),
    carrying just the attributes create_cursor() looks at.
    """
    connector = object.__new__(SSHConnector)
    connector.conn_inactivity = 1
    connector.last_activity_ts = last_activity_ts
    connector.conn = None
    return connector


def test_ispyb_exceptions_are_in_the_root_module():
    """12.x moved the exceptions out of 'ispyb.exception' and renamed them."""
    assert issubclass(ispyb.NoResult, ispyb.ISPyBException)
    assert issubclass(ispyb.ConnectionError, ispyb.ISPyBException)
    assert issubclass(ispyb.ReadWriteError, ispyb.ISPyBException)


def test_ispyb_exception_module_has_gone():
    """The old exception module must not be relied on anywhere."""
    with pytest.raises(ImportError):
        __import__("ispyb.exception")


def test_core_offers_a_visit_level_person_retrieval():
    """The reason for the upgrade - 'retrieve_persons_for_session()' takes the
    three parts of a target access string, i.e. "lb12345-1" is ("lb", "12345", "1").
    """
    signature = inspect.signature(Core.retrieve_persons_for_session)
    assert list(signature.parameters) == [
        "self",
        "proposal_code",
        "proposal_number",
        "visit_number",
    ]


def test_create_cursor_accepts_the_dictionary_keyword():
    """The parent class calls 'self.create_cursor(dictionary=True)' from
    'call_sf_retrieve()', so our override has to accept the keyword.
    """
    signature = inspect.signature(SSHConnector.create_cursor)
    assert "dictionary" in signature.parameters


def test_create_cursor_signature_matches_the_parent():
    """An incompatible override is what broke the stored-function methods."""
    parent_create_cursor = inspect.getattr_static(
        SSHConnector.__mro__[1], "create_cursor"
    )
    assert list(inspect.signature(SSHConnector.create_cursor).parameters) == list(
        inspect.signature(parent_create_cursor).parameters
    )


def test_create_cursor_rejects_a_connection_left_idle_too_long():
    """A connector is created (and stopped) for each request, so an idle
    connection cannot be re-established here - the caller must make a new one.
    """
    connector = _unconnected_connector(time.time() - 10)
    with pytest.raises(ispyb.ConnectionError):
        connector.create_cursor()


def test_create_cursor_rejects_a_stopped_connector():
    """stop() clears last_activity_ts."""
    connector = _unconnected_connector(None)
    with pytest.raises(ispyb.ConnectionError):
        connector.create_cursor()
