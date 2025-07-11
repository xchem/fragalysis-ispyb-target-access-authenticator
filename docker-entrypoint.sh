#!/usr/bin/env ash

#set -e

# Run the container using port 8080
echo "+> Launching uvicorn..."
uvicorn app.app:app --host 0.0.0.0 --port 8080
