#!/usr/bin/env bash

# A liveness probe.
# Live if there's a RUNNING file.

if [[ -f "${HOME}/RUNNING" ]]; then
  exit 0
else
  exit 1
fi
