#!/usr/bin/env ash

#set -e

# Run the container using port 8080
echo "+> Launching uvicorn..."
echo "+> WORKERS=${WORKERS}"
echo "+> CONCURRENCY=${CONCURRENCY}"
uvicorn app.app:app --host 0.0.0.0 --port 8080 \
    --workers ${WORKERS} \
    --limit-concurrency ${CONCURRENCY}
