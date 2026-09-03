#!/usr/bin/env bash
# Short form: ./cell4b.sh selftest  ==  .venv/bin/python -m cell4b selftest
cd "$(dirname "$0")"
exec .venv/bin/python -m cell4b "$@"
