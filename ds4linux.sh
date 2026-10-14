#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="${DS4LINUX_PYTHON:-$SCRIPT_DIR/venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="${DS4LINUX_PYTHON:-python3}"
fi
cd "$SCRIPT_DIR"
exec "$PYTHON" -m src.main "$@"
