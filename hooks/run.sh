#!/bin/sh
# Runs a guard with whichever Python works here (python3 on macOS and Linux,
# python on most Windows installs, where python3 can be a Store stub that fails).
# No Python at all: let the tool call through rather than block work.
if python3 -c "" >/dev/null 2>&1; then
  exec python3 "$(dirname "$0")/$1"
elif python -c "" >/dev/null 2>&1; then
  exec python "$(dirname "$0")/$1"
fi
exit 0
