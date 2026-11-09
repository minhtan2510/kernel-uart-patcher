#!/usr/bin/env bash
# ==============================================================================
# package_release.sh — Release Packaging Script for Kernel UART Patcher
#
# Packages the standalone executable and user guide into distributable
# archives (.tar.gz and .zip) with automated SHA256 checksum generation.
#
# Usage:
#   ./scripts/package_release.sh [version_tag]
#
# Examples:
#   ./scripts/package_release.sh v1.0.0
#   ./scripts/package_release.sh
# ==============================================================================

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

APP_NAME="Kernel_UART_Patcher"
GUIDE_FILE="USER_GUIDE.md"
RELEASE_DIR="$ROOT_DIR/release"

# 1. Determine release version
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    # Try git tag first, fallback to v1.0.0
    if command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null; then
        VERSION=$(git describe --tags --exact-match 2>/dev/null || git describe --tags 2>/dev/null || echo "v1.0.0")
    else
        VERSION="v1.0.0"
    fi
fi

# Ensure version starts with 'v'
if [[ ! "$VERSION" =~ ^v ]]; then
    VERSION="v${VERSION}"
fi

ARCH_NAME="Kernel-UART-Patcher-${VERSION}-linux-x86_64"

echo "======================================================================"
echo " Packaging Release: ${ARCH_NAME}"
echo "======================================================================"

# 2. Check executable binary (build automatically if missing)
if [ ! -f "$ROOT_DIR/$APP_NAME" ]; then
    echo "[*] Binary '$APP_NAME' not found. Building first via build.sh..."
    "$ROOT_DIR/scripts/build.sh"
fi

if [ ! -f "$ROOT_DIR/$APP_NAME" ]; then
    echo "[-] Error: Failed to find or build '$APP_NAME'."
    exit 1
fi

if [ ! -f "$ROOT_DIR/$GUIDE_FILE" ]; then
    echo "[-] Error: User guide file '$GUIDE_FILE' not found."
    exit 1
fi

# 3. Prepare release directory
mkdir -p "$RELEASE_DIR"
STAGE_DIR=$(mktemp -d "/tmp/${ARCH_NAME}.XXXXXX")

cleanup()
{
    if [ -d "${STAGE_DIR:-}" ]; then
        rm -rf "$STAGE_DIR"
    fi
}
trap cleanup EXIT

# 4. Stage release files into folder
PKG_DIR="$STAGE_DIR/$ARCH_NAME"
mkdir -p "$PKG_DIR"

echo "[*] Staging release files..."
cp -f "$ROOT_DIR/$APP_NAME" "$PKG_DIR/$APP_NAME"
chmod +x "$PKG_DIR/$APP_NAME"
cp -f "$ROOT_DIR/$GUIDE_FILE" "$PKG_DIR/USER_GUIDE.md"

# 5. Create compressed archives (.tar.gz and .zip)
echo "[*] Creating .tar.gz archive..."
TAR_FILE="$RELEASE_DIR/${ARCH_NAME}.tar.gz"
tar -czf "$TAR_FILE" -C "$STAGE_DIR" "$ARCH_NAME"

echo "[*] Creating .zip archive..."
ZIP_FILE="$RELEASE_DIR/${ARCH_NAME}.zip"
if command -v zip &>/dev/null; then
    (cd "$STAGE_DIR" && zip -qr "$ZIP_FILE" "$ARCH_NAME")
else
    # Fallback to python zipfile if zip utility is not installed
    python3 -c "
import zipfile, os
stage = '$STAGE_DIR'
arch = '$ARCH_NAME'
zip_path = '$ZIP_FILE'
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(os.path.join(stage, arch)):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, stage)
            zf.write(full, rel)
"
fi

# 6. Generate SHA256 Checksums
CHECKSUM_FILE="$RELEASE_DIR/checksums-${VERSION}.txt"
echo "[*] Generating SHA-256 checksums..."
cd "$RELEASE_DIR"
sha256sum "$(basename "$TAR_FILE")" "$(basename "$ZIP_FILE")" > "$CHECKSUM_FILE"

# 7. Print summary
echo "======================================================================"
echo "[✓] RELEASE PACKAGING COMPLETE!"
echo "======================================================================"
echo "Target Folder: $RELEASE_DIR"
echo ""
echo "Generated Archives:"
ls -lh "$TAR_FILE" "$ZIP_FILE" "$CHECKSUM_FILE" | awk '{print "  - " $9 " (" $5 ")"}'
echo ""
echo "Checksums (SHA256):"
cat "$CHECKSUM_FILE" | sed 's/^/  /'
echo "======================================================================"
