#!/usr/bin/env bash
# ==============================================================================
# run_gui.sh — Launcher for UART DTR/RTS Control Panel GUI
# ==============================================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

# Verify python3 is installed
if ! command -v python3 &>/dev/null; then
    echo "Lỗi: Chưa cài đặt python3 trên hệ thống."
    exit 1
fi

# Launch GUI
exec python3 "$SCRIPT_DIR/gui.py" "$@"
