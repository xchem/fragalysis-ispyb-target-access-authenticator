"""Configuration (environment) variables."""
import os


class Config:
    """Simple config module where all environment variables can be found."""

    CACHE_EXPIRY_MINUTES: int = int(os.environ.get("TAA_CACHE_EXPIRY_MINUTES", "2"))
    PING_CACHE_EXPIRY_SECONDS: int = int(
        os.environ.get("TAA_PING_CACHE_EXPIRY_SECONDS", "25")
    )

    ISPYB_HOST: str | None = os.environ.get("TAA_ISPYB_HOST")
    ISPYB_PORT: int | None = int(os.environ.get("TAA_ISPYB_PORT", "0"))
    ISPYB_USER: str | None = os.environ.get("TAA_ISPYB_USER")
    ISPYB_PASSWORD: str | None = os.environ.get("TAA_ISPYB_PASSWORD")
    ISPYB_DB: str = os.environ.get("TAA_ISPYB_DB", "db")
    ISPYB_CONN_INACTIVITY: int = int(os.environ.get("TAA_ISPYB_CONN_INACTIVITY", "360"))

    SSH_HOST: str | None = os.environ.get("TAA_SSH_HOST")
    SSH_USER: str | None = os.environ.get("TAA_SSH_USER")
    SSH_PASSWORD: str | None = os.environ.get("TAA_SSH_PASSWORD")
    SSH_PRIVATE_KEY_FILENAME: str | None = os.environ.get(
        "TAA_SSH_PRIVATE_KEY_FILENAME"
    )

    MEMCACHED_LOCATION: str = os.getenv("TAA_MEMCACHED_LOCATION", "localhost")

    QUERY_KEY: str | None = os.getenv("TAA_QUERY_KEY")

    TAS_CODES: str = os.environ.get("TAA_TAS_CODES", "lb")
    TAS_CODES_SET: set[str] = set(TAS_CODES.split(",")) if TAS_CODES else set()

    # Do we enable the built-in test user?
    ENABLE_DAVE_LISTER: bool = (
        os.environ.get("TAA_ENABLE_DAVE_LISTER", "no").lower() == "yes"
    )
