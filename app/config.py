"""Configuration (environment) variables."""
import os


class Config:
    """Simple config module where all environment variables can be found."""

    CACHE_EXPIRY_MINUTES: int = int(os.environ.get("CACHE_EXPIRY_MINUTES", "2"))

    ISPYB_HOST: str | None = os.environ.get("ISPYB_HOST")
    ISPYB_PORT: str | None = os.environ.get("ISPYB_PORT")
    ISPYB_USER: str | None = os.environ.get("ISPYB_USER")
    ISPYB_PASSWORD: str | None = os.environ.get("ISPYB_PASSWORD")
    ISPYB_DB: str = os.environ.get("ISPYB_DB", "db")
    ISPYB_CONN_INACTIVITY: int = int(os.environ.get("ISPYB_CONN_INACTIVITY", "360"))

    SSH_HOST: str | None = os.environ.get("SSH_HOST")
    SSH_USER: str | None = os.environ.get("SSH_USER")
    SSH_PASSWORD: str | None = os.environ.get("SSH_PASSWORD")
    SSH_PRIVATE_KEY_FILENAME: str | None = os.environ.get("SSH_PRIVATE_KEY_FILENAME")

    MEMCACHED_LOCATION: str = os.getenv("TAA_MEMCACHED_LOCATION", "localhost")

    QUERY_KEY: str | None = os.getenv("TAA_QUERY_KEY")
