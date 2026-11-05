#!/usr/bin/env bash
# ==============================================================================
# run.sh — Entry Point Launcher for UART Shield GUI
# ==============================================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

# Verify python3 is installed
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is not installed on this system."
    exit 1
fi

# Launch GUI from src/gui
exec python3 "$SCRIPT_DIR/src/gui/gui.py" "$@"
