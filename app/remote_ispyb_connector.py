import logging
import threading
import time
import traceback

import pymysql
import sshtunnel
from ispyb.connector.mysqlsp.main import ISPyBMySQLSPConnector as Connector
from ispyb.exception import (
    ISPyBConnectionException,
    ISPyBNoResultException,
    ISPyBRetrieveFailed,
)
from pymysql import Connection
from pymysql.cursors import Cursor
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
    def __init__(self):
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
                logger.warning("%s", repr(oe_e))
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
            raise ISPyBConnectionException
        self.last_activity_ts = time.time()

    def create_cursor(self):
        if (
            not self.last_activity_ts
            or time.time() - self.last_activity_ts > self.conn_inactivity
        ):
            # re-connect:
            self.connect(self.user, self.pw, self.host, self.db, self.port)
        self.last_activity_ts = time.time()
        if self.conn is None:
            raise ISPyBConnectionException

        cursor = self.conn.cursor(pymysql.cursors.DictCursor)
        if cursor is None:
            raise ISPyBConnectionException
        return cursor

    def call_sp_retrieve(self, procname, args):
        assert self.conn
        with self.lock:
            cursor = self.create_cursor()
            try:
                cursor.callproc(procname=procname, args=args)
            except self.conn.DataError as e:
                raise ISPyBRetrieveFailed(
                    f"DataError({e.errno}): {traceback.format_exc()}"
                ) from e

            result = cursor.fetchall()

            cursor.close()
        if result == []:
            raise ISPyBNoResultException
        return result

    def stop(self):
        if self.server is not None:
            self.server.stop()
        self.server = None
        self.conn = None
        self.last_activity_ts = None
        logger.debug("Server stopped")
