#!/bin/sh
set -eu
task_root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
task_python=$(command -v python3 || command -v python)
"$task_python" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
PYTHONPATH="$task_root/src" "$task_python" -m codex_bootstrap install
