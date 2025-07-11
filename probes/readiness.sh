#!/usr/bin/env bash

# A readiness probe.
# Live if there's a RUNNING file.

if [[ -f "${HOME}/RUNNING" ]]; then
  exit 0
else
  exit 1
fi
