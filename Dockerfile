# The default base image
ARG from_image=python:3.12.11-alpine3.22
FROM ${from_image} AS python-base

# Force the binary layer of the stdout and stderr streams
# to be unbuffered
ENV PYTHONUNBUFFERED=1

# Base directory for the application
# Also used for user directory
ENV APP_ROOT=/home/taa

WORKDIR ${APP_ROOT}

# another stage for poetry installation. this ensures poetry won't end
# up in final image where it's not needed
FROM python-base AS poetry-base
ARG POETRY_VERSION=1.8.5

RUN pip install --no-cache-dir poetry==${POETRY_VERSION}

WORKDIR /
COPY poetry.lock pyproject.toml /

# POETRY_VIRTUALENVS_IN_PROJECT tells poetry to create the venv to
# project's directory (.venv). This way the location is predictable
RUN POETRY_VIRTUALENVS_IN_PROJECT=true poetry install --no-root --only main --no-directory

# final stage. only copy the venv with installed packages and point
# paths to it
FROM python-base AS final

COPY --from=poetry-base /.venv /.venv

ENV PYTHONPATH="/.venv/lib/python3.12/site-packages/"
ENV PATH=/.venv/bin:$PATH

# Install tools for memcached.
# This allows us to run 'memdump -s localhost' to display all the keys.
RUN apk add libmemcached

COPY clear.py .
COPY stats.py .
COPY tas.py .
COPY app/ ./app/
COPY logging.config .
COPY docker-entrypoint.sh .
COPY VERSION .

# Probes...
COPY probes/*.sh .

# Create a base directory for file-based logging
WORKDIR /logs

# Switch to container user
ENV HOME=${APP_ROOT}
WORKDIR ${APP_ROOT}

# Workers (processes)
ENV WORKERS=1

# Start the application
CMD ["./docker-entrypoint.sh"]
