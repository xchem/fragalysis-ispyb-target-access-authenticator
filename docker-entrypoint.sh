#!/usr/bin/env ash

#set -e

# Run the container using both the customer-facing stats service
# and the internal authentication service endpoint.
# Done by launching two uvicorn instances in parallel.
echo "+> Launching uvicorn (x2)..."
echo "+> WORKERS=${WORKERS}"
uvicorn app.app:stats --host 0.0.0.0 --port 8081 & \
    uvicorn app.app:auth --host 0.0.0.0 --port 8080 --workers ${WORKERS}
