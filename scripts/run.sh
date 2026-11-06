#!/usr/bin/env bash
# ==============================================================================
# run.sh — Entry Point Launcher for Kernel UART Patcher GUI
# ==============================================================================

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

# Verify python3 is installed
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is not installed on this system."
    exit 1
fi

# Launch GUI from src/gui
exec python3 "$ROOT_DIR/src/gui/gui.py" "$@"
