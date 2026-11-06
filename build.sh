#!/usr/bin/env bash
# ==============================================================================
# build.sh — Standalone Single Executable Packager for Kernel UART Patcher
#
# Generates a standalone single-file ELF executable binary via PyInstaller
# identical to the packaging format of 'Gremsy Firmware Debug Tools'.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

OUTPUT_NAME="Kernel UART Patcher"

echo "======================================================================"
echo " Packaging: $OUTPUT_NAME (Standalone ELF Binary)"
echo "======================================================================"

# 1. Ensure Python 3 is available
if ! command -v python3 &>/dev/null; then
    echo "[-] Error: python3 is required to build."
    exit 1
fi

# 2. Check / install PyInstaller
PYINSTALLER_BIN=""
if command -v pyinstaller &>/dev/null; then
    PYINSTALLER_BIN="pyinstaller"
elif [ -f "$HOME/.local/bin/pyinstaller" ]; then
    PYINSTALLER_BIN="$HOME/.local/bin/pyinstaller"
else
    echo "[*] PyInstaller not found. Installing via pip..."
    python3 -m pip install --user pyinstaller
    PYINSTALLER_BIN="$HOME/.local/bin/pyinstaller"
fi

echo "[+] Using PyInstaller: $($PYINSTALLER_BIN --version)"

# 3. Clean previous build artifacts
echo "[*] Cleaning old build artifacts..."
rm -rf build dist "$OUTPUT_NAME.spec"

# 4. Build single-file executable
echo "[*] Compiling and packaging single-file executable binary..."
"$PYINSTALLER_BIN" \
    --name "$OUTPUT_NAME" \
    --onefile \
    --windowed \
    --add-data "src/core/uart_kernel_patch.sh:core" \
    --add-data "src/core/patch_driver.py:core" \
    --clean \
    --noconfirm \
    src/gui/gui.py

# 5. Verify output
TARGET_BINARY="$SCRIPT_DIR/dist/$OUTPUT_NAME"
if [ -f "$TARGET_BINARY" ]; then
    chmod +x "$TARGET_BINARY"
    # Copy to root directory for convenient single-click execution
    cp -f "$TARGET_BINARY" "$SCRIPT_DIR/$OUTPUT_NAME"
    chmod +x "$SCRIPT_DIR/$OUTPUT_NAME"

    FILE_SIZE=$(du -h "$SCRIPT_DIR/$OUTPUT_NAME" | cut -f1)
    echo "======================================================================"
    echo "[✓] SUCCESS: Single-file binary created successfully!"
    echo "    - Output: $SCRIPT_DIR/$OUTPUT_NAME"
    echo "    - Format: $(file -b "$SCRIPT_DIR/$OUTPUT_NAME" | cut -d, -f1)"
    echo "    - Size:   $FILE_SIZE"
    echo "======================================================================"
    echo "You can now run it directly by double-clicking or executing:"
    echo "    ./\"$OUTPUT_NAME\""
else
    echo "[-] Error: Build failed, binary not found in dist/"
    exit 1
fi

