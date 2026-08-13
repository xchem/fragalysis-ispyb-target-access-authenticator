"""Handle logic connecting to the ISPyB server & database"""

import logging
import threading
import time
import traceback

import ispyb
import pymysql
import sshtunnel
from ispyb.connector.mysqlsp.main import ISPyBMySQLSPConnector as Connector
from pymysql import Connection
from pymysql.cursors import Cursor, DictCursor
from pymysql.err import OperationalError

from .config import Config
from .prometheus_metrics import PrometheusMetrics

logger: logging.Logger = logging.getLogger(__name__)

# Timeout to allow the pymysql.connect() method to connect to the DB.
# The default, if not specified, is 10 seconds.
PYMYSQL_CONNECT_TIMEOUT_S = 3
PYMYSQL_READ_TIMEOUT_S = 3
PYMYSQL_WRITE_TIMEOUT_S = 10
# MySQL DB connection attempts.
# An attempt to cope with intermittent OperationalError exceptions
# that are seen to occur at "busy times". See m2ms-1403.
PYMYSQL_OE_RECONNECT_ATTEMPTS = 5
PYMYSQL_EXCEPTION_RECONNECT_DELAY_S = 1


class SSHConnector(Connector):
    """An SSH connector.

    We deliberately do not use the parent's connection handling - it connects
    directly with mysql.connector and knows nothing about our SSH tunnel.
    We build our own pymysql connection in remote_connect() instead, which is
    why the parent's __init__() is not called and its abstract '_notimplemented'
    is left alone.
    """

    # 'abstract-method' - the parent's '_notimplemented' is not on our path.
    # 'unsubscriptable-object' - pymysql's Connection is only subscriptable
    # to a type-checker, and the annotation is never evaluated at runtime.
    # pylint: disable=abstract-method,unsubscriptable-object

    def __init__(self):  # pylint: disable=super-init-not-called
        self.conn_inactivity = Config.ISPYB_CONN_INACTIVITY
        self.lock: threading.Lock = threading.Lock()
        self.conn: Connection[Cursor] | None = None
        self.server: sshtunnel.SSHTunnelForwarder | None = None
        self.last_activity_ts: float | None = None

        creds = {
            "ssh_host": Config.SSH_HOST,
            "ssh_user": Config.SSH_USER,
            "ssh_pass": Config.SSH_PASSWORD,
            "ssh_pkey": Config.SSH_PRIVATE_KEY_FILENAME,
            "db_host": Config.ISPYB_HOST,
            "db_port": Config.ISPYB_PORT,
            "db_user": Config.ISPYB_USER,
            "db_pass": Config.ISPYB_PASSWORD,
            "db_name": Config.ISPYB_DB,
        }
        logger.debug("Creating remote connector: %s", creds)
        self.remote_connect(**creds)
        assert self.server
        logger.debug(
            "Started remote ssh_host=%s ssh_user=%s local_bind_port=%s",
            Config.SSH_HOST,
            Config.SSH_USER,
            self.server.local_bind_port,
        )

    def remote_connect(
        self,
        ssh_host,
        ssh_user,
        ssh_pass,
        ssh_pkey,
        db_host,
        db_port,
        db_user,
        db_pass,
        db_name,
    ):
        """Connect to the remote server"""
        sshtunnel.SSH_TIMEOUT = 5.0
        sshtunnel.TUNNEL_TIMEOUT = 5.0
        sshtunnel.DEFAULT_LOGLEVEL = logging.ERROR
        self.conn_inactivity = int(self.conn_inactivity)

        if ssh_pkey:
            logger.debug(
                "Creating SSHTunnelForwarder (with SSH Key) host=%s user=%s",
                ssh_host,
                ssh_user,
            )
            self.server = sshtunnel.SSHTunnelForwarder(
                (ssh_host),
                ssh_username=ssh_user,
                ssh_pkey=ssh_pkey,
                remote_bind_address=(db_host, db_port),
            )
        else:
            logger.debug(
                "Creating SSHTunnelForwarder (with password) host=%s user=%s",
                ssh_host,
                ssh_user,
            )
            self.server = sshtunnel.SSHTunnelForwarder(
                (ssh_host),
                ssh_username=ssh_user,
                ssh_password=ssh_pass,
                remote_bind_address=(db_host, db_port),
            )
        logger.debug("Created SSHTunnelForwarder")

        # stops hanging connections in transport
        assert self.server
        self.server.daemon_forward_servers = True
        self.server.daemon_transport = True

        logger.debug("Starting SSH server...")
        self.server.start()
        PrometheusMetrics.new_tunnel()
        logger.debug("Started SSH server")

        # Try to connect to the database
        # a number of times (because it is known to fail)
        # before giving up...
        connect_attempts = 0
        self.conn = None
        while self.conn is None and connect_attempts < PYMYSQL_OE_RECONNECT_ATTEMPTS:
            try:
                self.conn = pymysql.connect(
                    user=db_user,
                    password=db_pass,
                    host="127.0.0.1",
                    port=self.server.local_bind_port,
                    database=db_name,
                    connect_timeout=PYMYSQL_CONNECT_TIMEOUT_S,
                    read_timeout=PYMYSQL_READ_TIMEOUT_S,
                    write_timeout=PYMYSQL_WRITE_TIMEOUT_S,
                )
            except OperationalError as oe_e:
                if connect_attempts == 0:
                    # So we only log our connection attempts once
                    # an error has occurred - to avoid flooding the log
                    logger.debug(
                        "Connecting to MySQL database (db_user=%s db_name=%s)...",
                        db_user,
                        db_name,
                    )
                logger.debug("%s", repr(oe_e))
                connect_attempts += 1
                PrometheusMetrics.new_ispyb_connection_attempt()
                time.sleep(PYMYSQL_EXCEPTION_RECONNECT_DELAY_S)
            except Exception as e:  # pylint: disable=broad-exception-caught
                if connect_attempts == 0:
                    # So we only log our connection attempts once
                    # an error has occurred - to avoid flooding the log
                    logger.debug(
                        "Connecting to MySQL database (db_user=%s db_name=%s)...",
                        db_user,
                        db_name,
                    )
                logger.warning("Unexpected %s", repr(e))
                connect_attempts += 1
                PrometheusMetrics.new_ispyb_connection_attempt()
                time.sleep(PYMYSQL_EXCEPTION_RECONNECT_DELAY_S)

        if self.conn is not None:
            if connect_attempts > 0:
                logger.debug("Connected")
            PrometheusMetrics.new_ispyb_connection()
        else:
            if connect_attempts > 0:
                logger.warning("Failed to connect")
            PrometheusMetrics.failed_ispyb_connection()
            self.server.stop()
            raise ispyb.ConnectionError
        self.last_activity_ts = time.time()

    def create_cursor(self, dictionary=False):
        """Create a server/db cursor.
        The parent class calls this with 'dictionary=True' when it needs rows
        returned as dictionaries rather than tuples.
        """
        if (
            not self.last_activity_ts
            or time.time() - self.last_activity_ts > self.conn_inactivity
        ):
            # The connection has been stopped, or left idle for too long.
            # We cannot re-connect here - the parent's connect() knows nothing
            # about our SSH tunnel - so the caller has to create a new connector.
            logger.debug("Connection is not usable (stopped or idle too long)")
            raise ispyb.ConnectionError
        self.last_activity_ts = time.time()
        if self.conn is None:
            raise ispyb.ConnectionError

        cursor = self.conn.cursor(DictCursor if dictionary else Cursor)
        if cursor is None:
            raise ispyb.ConnectionError
        return cursor

    def call_sp_retrieve(self, procname, args):
        """Retrieve server results"""
        assert self.conn
        with self.lock:
            # Rows are returned as dictionaries (keyed on column name),
            # which is what the callers of the 'core' methods expect.
            cursor = self.create_cursor(dictionary=True)
            try:
                cursor.callproc(procname=procname, args=args)
            except self.conn.DataError as e:
                raise ispyb.ReadWriteError(
                    f"DataError({e}): {traceback.format_exc()}"
                ) from e

            result = cursor.fetchall()

            cursor.close()
        if result == []:
            raise ispyb.NoResult
        return result

    def stop(self):
        """Stop the server"""
        if self.server is not None:
            self.server.stop()
        self.server = None
        self.conn = None
        self.last_activity_ts = None
        logger.debug("Server stopped")
