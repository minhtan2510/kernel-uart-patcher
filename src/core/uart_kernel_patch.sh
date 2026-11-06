#!/usr/bin/env bash
# ==============================================================================
# uart_kernel_patch.sh
#
# Deep Patch for Linux USB Serial Drivers to completely neutralize DTR/RTS assertion.
#
# Why a Deep Patch is needed:
#   Simply commenting out .dtr_rts is NOT enough because:
#   1. When user applications (PySerial, QtSerialPort, Gimbal GUI) connect,
#      they explicitly invoke ioctl(TIOCMSET) / ioctl(TIOCMBIS) with TIOCM_DTR,
#      which calls the driver's .tiocmset callback to drive DTR LOW!
#   2. During port_open, the driver enables the UART interface, resetting
#      modem control signals unless explicitly commanded to remain HIGH.
#   3. Flow control configuration in set_termios can still assert DTR.
#
# The Deep Patch operates at 5 levels:
#   1. Adds module parameter 'disable_dtr_rts' (default: true).
#      Can be toggled live via /sys/module/<name>/parameters/disable_dtr_rts!
#   2. On port_open: explicitly commands chip to hold DTR/RTS HIGH (inactive 3.3V).
#   3. On tiocmset (ioctl TIOCMSET/TIOCMBIS): strips TIOCM_DTR and TIOCM_RTS
#      from the set mask, blocking all userspace apps from asserting DTR.
#   4. On dtr_rts callback: always forces DTR/RTS inactive regardless of 'on'.
#   5. On flow control: guarantees DTR/RTS are never set to active.
#
# Supported: cp210x, ch341, ftdi_sio, pl2303, cdc_acm
#
# Usage:
#   sudo ./uart_kernel_patch.sh patch   /dev/ttyUSB0
#   sudo ./uart_kernel_patch.sh patch   cp210x
#   sudo ./uart_kernel_patch.sh restore cp210x
#   sudo ./uart_kernel_patch.sh toggle  cp210x 0|1
#   ./uart_kernel_patch.sh status
# ==============================================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT_NAME=$(basename "$0")
BACKUP_DIR="/var/backups/uart_dtr_patch"

# Kernel version info
KVER=$(uname -r)
KVER_SHORT=$(echo "$KVER" | grep -oP '^\d+\.\d+\.\d+' || echo "$KVER")
KVER_BRANCH=$(echo "$KVER" | grep -oP '^\d+\.\d+' || echo "$KVER")

# Colors
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
BOLD='\033[1m'
NC='\033[0m'

# State
MODULE=""
MOD_SRCDIR=""
MOD_FILESTEM=""
MOD_EXTRA_FILES=()
WORK_DIR=""
AUTO_CONFIRM=false

# ==============================================================================
# Helpers
# ==============================================================================

info() { echo -e "  ${GREEN}[OK]${NC} $*"; }
warn() { echo -e "  ${YELLOW}[!!]${NC} $*"; }
err()  { echo -e "  ${RED}[ERR]${NC} $*" >&2; }

die()
{
    err "$@"
    exit 1
}

cleanup()
{
    if [ -n "${WORK_DIR:-}" ] && [ -d "${WORK_DIR:-}" ]; then
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

# ==============================================================================
# Module info lookup
# ==============================================================================

set_module_info()
{
    MOD_EXTRA_FILES=()
    case "$MODULE" in
        ch341)
            MOD_SRCDIR="drivers/usb/serial"
            MOD_FILESTEM="ch341"
            ;;
        cp210x)
            MOD_SRCDIR="drivers/usb/serial"
            MOD_FILESTEM="cp210x"
            ;;
        ftdi_sio)
            MOD_SRCDIR="drivers/usb/serial"
            MOD_FILESTEM="ftdi_sio"
            MOD_EXTRA_FILES=("ftdi_sio.h" "ftdi_sio_ids.h")
            ;;
        pl2303)
            MOD_SRCDIR="drivers/usb/serial"
            MOD_FILESTEM="pl2303"
            MOD_EXTRA_FILES=("pl2303.h")
            ;;
        cdc_acm|cdc-acm)
            MODULE="cdc_acm"
            MOD_SRCDIR="drivers/usb/class"
            MOD_FILESTEM="cdc-acm"
            MOD_EXTRA_FILES=("cdc-acm.h")
            ;;
        *)
            die "Unsupported module: $MODULE" \
                "\n         Supported: cp210x, ch341, ftdi_sio, pl2303, cdc_acm"
            ;;
    esac
}

# ==============================================================================
# Resolve module from port path or direct name
# ==============================================================================

resolve_module()
{
    local input="$1"

    if [[ "$input" == /dev/* ]]; then
        local port_name
        port_name=$(basename "$input")

        if [ ! -e "$input" ]; then
            die "Device $input does not exist. Is the USB adapter plugged in?"
        fi

        # Method 1: sysfs module symlink
        local mod_link="/sys/class/tty/${port_name}/device/driver/module"
        if [ -L "$mod_link" ]; then
            MODULE=$(basename "$(readlink -f "$mod_link")")
            set_module_info
            return
        fi

        # Method 2: walk parent devices in sysfs
        local dev_path
        dev_path=$(readlink -f "/sys/class/tty/${port_name}/device" 2>/dev/null || echo "")
        if [ -n "$dev_path" ]; then
            local cur="$dev_path"
            while [ "$cur" != "/" ] && [ "$cur" != "." ]; do
                if [ -L "${cur}/driver/module" ]; then
                    local mod
                    mod=$(basename "$(readlink -f "${cur}/driver/module")")
                    case "$mod" in
                        ch341|cp210x|ftdi_sio|pl2303|cdc_acm)
                            MODULE="$mod"
                            set_module_info
                            return
                            ;;
                    esac
                fi
                cur=$(dirname "$cur")
            done
        fi

        # Method 3: check loaded modules
        local loaded_mods=()
        for mod in ch341 cp210x ftdi_sio pl2303 cdc_acm; do
            if [ -d "/sys/module/${mod}" ]; then
                loaded_mods+=("$mod")
            fi
        done

        if [ ${#loaded_mods[@]} -eq 1 ]; then
            MODULE="${loaded_mods[0]}"
            set_module_info
            return
        elif [ ${#loaded_mods[@]} -gt 1 ]; then
            die "Multiple USB serial modules loaded: ${loaded_mods[*]}" \
                "\n         Specify directly: sudo $SCRIPT_NAME patch <module_name>"
        fi

        die "Cannot detect module for $input." \
            "\n         Specify directly: sudo $SCRIPT_NAME patch cp210x"
    else
        MODULE="${input//-/_}"
        set_module_info
    fi
}

# ==============================================================================
# Secure Boot check
# ==============================================================================

check_secure_boot()
{
    if command -v mokutil &>/dev/null; then
        if mokutil --sb-state 2>/dev/null | grep -qi "enabled"; then
            echo ""
            warn "Secure Boot is ${RED}ENABLED${NC}"
            warn "Loading unsigned kernel modules will fail."
            warn "Options:"
            warn "  1. Disable Secure Boot in BIOS/UEFI"
            warn "  2. Sign the module with a MOK key"
            echo ""
            if ! $AUTO_CONFIRM; then
                read -rp "  Continue anyway? [y/N] " reply
                if [[ ! "${reply:-}" =~ ^[Yy]$ ]]; then
                    echo "  Aborted."
                    exit 0
                fi
            fi
            echo ""
        fi
    fi
}

# ==============================================================================
# Check and install dependencies
# ==============================================================================

check_deps()
{
    local missing=()

    # Kernel headers
    if [ ! -d "/lib/modules/${KVER}/build" ]; then
        missing+=("linux-headers-${KVER}")
    fi

    # Build tools
    if ! command -v make &>/dev/null || ! command -v gcc &>/dev/null; then
        missing+=("build-essential")
    fi

    # Curl
    if ! command -v curl &>/dev/null; then
        missing+=("curl")
    fi

    # Python3
    if ! command -v python3 &>/dev/null; then
        missing+=("python3")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        local unique
        unique=($(printf '%s\n' "${missing[@]}" | sort -u))

        warn "Missing packages: ${unique[*]}"
        echo ""
        if ! $AUTO_CONFIRM; then
            read -rp "  Install now? [Y/n] " reply
            if [[ "${reply:-}" =~ ^[Nn]$ ]]; then
                die "Cannot proceed without: ${unique[*]}"
            fi
        fi
        echo ""

        apt-get update -qq
        apt-get install -y "${unique[@]}"
        echo ""
    fi

    info "Build tools & headers satisfied"
}

# ==============================================================================
# Extract or download driver source
# ==============================================================================

prepare_source()
{
    WORK_DIR=$(mktemp -d /tmp/uart_dtr_patch.XXXXXX)
    mkdir -p "$WORK_DIR/build"

    # Step A: Check local kernel source tarball
    local ksrc_tar=""
    for f in /usr/src/linux-source-"${KVER_SHORT}".tar.* \
             /usr/src/linux-source-"${KVER_BRANCH}".tar.* \
             /usr/src/linux-source-*.tar.*; do
        if [ -f "$f" ]; then
            ksrc_tar="$f"
            break
        fi
    done

    if [ -n "$ksrc_tar" ] && [ -f "$ksrc_tar" ]; then
        info "Found local source: $(basename "$ksrc_tar")"
        local ksrc_prefix
        ksrc_prefix=$(tar tf "$ksrc_tar" 2>/dev/null | head -1 | cut -d/ -f1)
        if [ -n "$ksrc_prefix" ]; then
            if tar xf "$ksrc_tar" -C "$WORK_DIR" "${ksrc_prefix}/${MOD_SRCDIR}/" 2>/dev/null; then
                cp "$WORK_DIR/${ksrc_prefix}/${MOD_SRCDIR}/"* "$WORK_DIR/build/" 2>/dev/null || true
            fi
        fi
    fi

    # Step B: If main .c file not extracted, download from git.kernel.org
    if [ ! -f "$WORK_DIR/build/${MOD_FILESTEM}.c" ]; then
        info "Fetching ${MOD_FILESTEM}.c from git.kernel.org (v${KVER_BRANCH}) ..."
        local base_url="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/${MOD_SRCDIR}"
        local target_url="${base_url}/${MOD_FILESTEM}.c?h=v${KVER_BRANCH}"

        if ! curl -sSf "$target_url" -o "$WORK_DIR/build/${MOD_FILESTEM}.c"; then
            target_url="${base_url}/${MOD_FILESTEM}.c?h=v${KVER_SHORT}"
            if ! curl -sSf "$target_url" -o "$WORK_DIR/build/${MOD_FILESTEM}.c"; then
                die "Failed to download ${MOD_FILESTEM}.c from git.kernel.org"
            fi
        fi

        for extra in "${MOD_EXTRA_FILES[@]}"; do
            info "Fetching $extra ..."
            curl -sSf "${base_url}/${extra}?h=v${KVER_BRANCH}" \
                 -o "$WORK_DIR/build/${extra}" || \
            curl -sSf "${base_url}/${extra}?h=v${KVER_SHORT}" \
                 -o "$WORK_DIR/build/${extra}" || true
        done
    fi

    if [ ! -f "$WORK_DIR/build/${MOD_FILESTEM}.c" ]; then
        die "Source file ${MOD_FILESTEM}.c could not be prepared"
    fi

    info "Source ready for ${MOD_FILESTEM}.c"
}

# ==============================================================================
# Apply Deep Patch
# ==============================================================================

patch_source()
{
    local src_file="$WORK_DIR/build/${MOD_FILESTEM}.c"
    local patch_script="$SCRIPT_DIR/patch_driver.py"

    if [ ! -f "$patch_script" ]; then
        die "Patch script $patch_script not found"
    fi

    info "Applying Deep Patch (parameter + open + tiocmset + dtr_rts + flow) ..."

    if ! python3 "$patch_script" "$MODULE" "$src_file"; then
        die "Failed to apply deep patch to $src_file"
    fi

    info "Deep patch applied successfully"
}

# ==============================================================================
# Build patched module out-of-tree
# ==============================================================================

build_module()
{
    local kdir="/lib/modules/${KVER}/build"
    local build_dir="$WORK_DIR/build"

    if [ ! -d "$kdir" ]; then
        die "Kernel headers not found at $kdir"
    fi

    echo "obj-m := ${MOD_FILESTEM}.o" > "$build_dir/Makefile"

    info "Building ${MOD_FILESTEM}.ko (kernel ${KVER}) ..."

    local build_log="$WORK_DIR/build.log"

    if ! make -C "$kdir" M="$build_dir" modules > "$build_log" 2>&1; then
        err "Build failed. Last 20 lines of build log:"
        echo ""
        tail -20 "$build_log" >&2
        echo ""
        die "Module build failed. See log above."
    fi

    local ko_file="$build_dir/${MOD_FILESTEM}.ko"
    if [ ! -f "$ko_file" ]; then
        die "Built module not found: ${MOD_FILESTEM}.ko"
    fi

    local ko_size
    ko_size=$(du -h "$ko_file" | cut -f1)
    info "Built: ${MOD_FILESTEM}.ko (${ko_size})"
}

# ==============================================================================
# Safe Module Unload & Rebind Helpers
# ==============================================================================

unload_module_safely()
{
    local mod="$1"

    # Step 1: Unbind all USB interfaces bound to this driver
    for dev_path in /sys/bus/usb/drivers/"${mod}"/*:*; do
        if [ -e "$dev_path" ]; then
            local dev_id
            dev_id=$(basename "$dev_path")
            info "Unbinding USB device $dev_id from ${mod} driver ..."
            echo "$dev_id" > "/sys/bus/usb/drivers/${mod}/unbind" 2>/dev/null || true
        fi
    done

    # Step 2: Unbind all tty ports from USB-serial driver
    for dev_path in /sys/bus/usb-serial/drivers/"${mod}"/ttyUSB*; do
        if [ -e "$dev_path" ]; then
            local dev_id
            dev_id=$(basename "$dev_path")
            echo "$dev_id" > "/sys/bus/usb-serial/drivers/${mod}/unbind" 2>/dev/null || true
        fi
    done
    sleep 1

    # Step 3: Unload module from kernel RAM
    if [ -d "/sys/module/${mod}" ]; then
        info "Unloading ${mod} from kernel RAM ..."
        if ! rmmod "$mod" 2>/dev/null; then
            warn "Module ${mod} is in use by an active process."
            warn "Please UNPLUG the USB cable of your Gimbal right now, then press Enter."
            read -r
            if ! rmmod "$mod"; then
                die "Failed to unload ${mod}. Ensure no terminal/app is holding /dev/ttyUSB* open!"
            fi
        fi
    fi

    # Verify that module is genuinely removed from RAM
    if [ -d "/sys/module/${mod}" ]; then
        die "Module ${mod} is still resident in kernel memory!"
    fi

    info "Module ${mod} unloaded cleanly from RAM"
}

rebind_devices()
{
    local mod="$1"
    for dev_path in /sys/bus/usb/devices/*:*; do
        if [ -e "$dev_path" ]; then
            local dev_id
            dev_id=$(basename "$dev_path")
            if [ -f "/sys/bus/usb/drivers/${mod}/bind" ]; then
                echo "$dev_id" > "/sys/bus/usb/drivers/${mod}/bind" 2>/dev/null || true
            fi
        fi
    done
}

# ==============================================================================
# Backup original, install patched module, reload
# ==============================================================================

install_module()
{
    local ko_file="$WORK_DIR/build/${MOD_FILESTEM}.ko"

    local orig_path
    orig_path=$(modinfo -F filename "$MODULE" 2>/dev/null || echo "")

    if [ -z "$orig_path" ] || [ "$orig_path" = "(builtin)" ]; then
        die "Module $MODULE is built-in or not found."
    fi

    info "Original location: $orig_path"

    # Backup original module
    mkdir -p "$BACKUP_DIR"
    local backup_file="$BACKUP_DIR/$(basename "$orig_path").orig"

    if [ ! -f "$backup_file" ]; then
        cp "$orig_path" "$backup_file"
        echo "$KVER" > "$BACKUP_DIR/${MODULE}.kver"
        echo "$orig_path" > "$BACKUP_DIR/${MODULE}.path"
        info "Backed up original module: $backup_file"
    else
        warn "Backup already exists, preserving previous original backup"
    fi

    # Confirm before reloading
    echo ""
    warn "${BOLD}Ensure NO application is currently using ${MODULE} before reloading.${NC}"
    echo ""
    if ! $AUTO_CONFIRM; then
        read -rp "  Ready to install and reload module? [Y/n] " reply
        if [[ "${reply:-}" =~ ^[Nn]$ ]]; then
            echo ""
            info "Patched module saved to: $ko_file"
            info "Manual install:"
            info "  sudo rmmod $MODULE"
            info "  sudo cp $ko_file $orig_path"
            info "  sudo depmod -a"
            info "  sudo modprobe $MODULE"
            echo ""
            return
        fi
    fi

    # Unload module safely from RAM
    unload_module_safely "$MODULE"

    # Install patched module to disk
    if [[ "$orig_path" == *.zst ]]; then
        zstd -f -q "$ko_file" -o "${ko_file}.zst"
        cp "${ko_file}.zst" "$orig_path"
    elif [[ "$orig_path" == *.xz ]]; then
        xz -f -k -q "$ko_file"
        cp "${ko_file}.xz" "$orig_path"
    elif [[ "$orig_path" == *.gz ]]; then
        gzip -f -k -q "$ko_file"
        cp "${ko_file}.gz" "$orig_path"
    else
        cp "$ko_file" "$orig_path"
    fi

    info "Installed patched module to $orig_path"

    # Rebuild module dependency database
    depmod -a "$KVER"

    # Load patched module into kernel RAM
    info "Loading patched module into kernel RAM ..."
    if modprobe "$MODULE"; then
        info "Loaded patched module into kernel memory!"
    else
        err "Failed to load module. Restoring backup..."
        cp "$backup_file" "$orig_path"
        depmod -a "$KVER"
        modprobe "$MODULE" 2>/dev/null || true
        die "Module load failed. Original restored."
    fi

    # Verify that the new module is genuinely active in kernel RAM
    if [ -f "/sys/module/${MODULE}/parameters/disable_dtr_rts" ]; then
        info "CONFIRMED: Deep Patch is ACTIVE in running kernel memory!"
        chmod 0666 "/sys/module/${MODULE}/parameters/disable_dtr_rts" 2>/dev/null || true
    else
        err "Verification failed: /sys/module/${MODULE}/parameters/disable_dtr_rts was not found."
        err "The patched module could not be activated in kernel memory."
        die "Deep Patch verification failed in running kernel memory!"
    fi

    # Install persistent udev rule so parameter stays writable without root password
    local udev_file="/etc/udev/rules.d/99-kernel-uart-patcher.rules"
    cat << 'EOF' > "$udev_file"
# Kernel UART Patcher: allow userspace to toggle DTR/RTS protection without root password
ACTION=="add", SUBSYSTEM=="module", KERNEL=="cp210x|ch341|ftdi_sio|pl2303|cdc_acm", RUN+="/bin/sh -c 'chmod 0666 /sys/module/%k/parameters/disable_dtr_rts 2>/dev/null || true'"
ACTION=="add", SUBSYSTEM=="tty", KERNEL=="ttyUSB*|ttyACM*", RUN+="/bin/sh -c 'chmod 0666 /sys/module/*/parameters/disable_dtr_rts 2>/dev/null || true'"
EOF
    udevadm control --reload-rules 2>/dev/null || true

    # Rebind devices
    rebind_devices "$MODULE"
}

# ==============================================================================
# Commands
# ==============================================================================

cmd_patch()
{
    echo -e "\n${BOLD}=== Deep Patching kernel module: ${MODULE} (${MOD_FILESTEM}) ===${NC}\n"

    check_secure_boot
    check_deps
    prepare_source
    patch_source
    build_module
    install_module

    echo ""
    echo -e "  ${GREEN}${BOLD}✓ Deep Patch completed successfully!${NC}"
    echo ""
    echo "  Features active in new driver:"
    echo "    - DTR and RTS are forced HIGH (inactive 3.3V) on open"
    echo "    - ioctl(TIOCMSET/TIOCMBIS) DTR/RTS requests from apps are blocked"
    echo "    - Parameter disable_dtr_rts is active: /sys/module/${MODULE}/parameters/disable_dtr_rts"
    echo ""
    warn "Unplug and replug your USB-UART adapter (or Gimbal) to apply."
    echo ""
    echo -e "  Live toggle (without recompile or reload):"
    echo -e "    ${CYAN}sudo ./$SCRIPT_NAME toggle $MODULE 0${NC}   (re-enable DTR/RTS)"
    echo -e "    ${CYAN}sudo ./$SCRIPT_NAME toggle $MODULE 1${NC}   (disable DTR/RTS)"
    echo ""
    echo -e "  To restore original kernel driver:"
    echo -e "    ${CYAN}sudo ./$SCRIPT_NAME restore $MODULE${NC}"
    echo ""
}

# ==============================================================================
# Recover Stock Module (Self-Healing Fallback when backup file is missing)
# ==============================================================================

recover_stock_module()
{
    local target_backup="$1"
    local target_orig="$2"

    warn "Backup file not found at: $target_backup"

    if ! $AUTO_CONFIRM; then
        echo ""
        warn "Local backup file does not exist in $BACKUP_DIR."
        read -rp "  Do you want to download and restore official stock driver from Ubuntu APT? [y/N] " reply
        if [[ ! "${reply:-}" =~ ^[Yy]$ ]]; then
            echo ""
            info "Restore operation cancelled."
            exit 0
        fi
        echo ""
    fi

    info "Attempting self-healing recovery: fetching official stock driver from package repository..."

    # Method 1: Query dpkg for the package owning the driver
    local pkg=""
    if command -v dpkg >/dev/null 2>&1; then
        pkg=$(dpkg -S "$target_orig" 2>/dev/null | cut -d: -f1 | head -n 1 || true)
        if [ -z "$pkg" ]; then
            local mod_base
            mod_base=$(basename "$target_orig")
            pkg=$(dpkg -S "*/${mod_base}" 2>/dev/null | grep "$KVER" | cut -d: -f1 | head -n 1 || true)
        fi
    fi

    if [ -n "$pkg" ]; then
        info "Identified parent kernel package: $pkg"
        local recover_dir
        recover_dir=$(mktemp -d /tmp/uart_stock_recover.XXXXXX)

        info "Downloading official deb package via apt-get ..."
        if (cd "$recover_dir" && apt-get download "$pkg" >/dev/null 2>&1); then
            local deb_file
            deb_file=$(find "$recover_dir" -name "*.deb" | head -n 1)
            if [ -n "$deb_file" ] && [ -f "$deb_file" ]; then
                info "Extracting official stock driver from $(basename "$deb_file") ..."
                mkdir -p "$recover_dir/extracted"
                dpkg-deb -x "$deb_file" "$recover_dir/extracted"

                local extracted_ko
                extracted_ko=$(find "$recover_dir/extracted" -name "$(basename "$target_orig")" | head -n 1)
                if [ -n "$extracted_ko" ] && [ -f "$extracted_ko" ]; then
                    mkdir -p "$BACKUP_DIR"
                    cp "$extracted_ko" "$target_backup"
                    echo "$KVER" > "$BACKUP_DIR/${MODULE}.kver"
                    echo "$target_orig" > "$BACKUP_DIR/${MODULE}.path"
                    info "Successfully recovered official stock driver into backup cache!"
                fi
            fi
        fi
        rm -rf "$recover_dir"
    fi

    # Method 2: Fallback to compiling clean unpatched source (if offline or apt failed)
    if [ ! -f "$target_backup" ]; then
        info "APT download unavailable. Attempting to build clean unpatched module from source..."
        prepare_source
        if build_module; then
            local clean_ko="$WORK_DIR/build/${MOD_FILESTEM}.ko"
            if [ -f "$clean_ko" ]; then
                mkdir -p "$BACKUP_DIR"
                if [[ "$target_orig" == *.zst ]]; then
                    zstd -f -q "$clean_ko" -o "${clean_ko}.zst"
                    cp "${clean_ko}.zst" "$target_backup"
                elif [[ "$target_orig" == *.xz ]]; then
                    xz -f -k -q "$clean_ko"
                    cp "${clean_ko}.xz" "$target_backup"
                elif [[ "$target_orig" == *.gz ]]; then
                    gzip -f -k -q "$clean_ko"
                    cp "${clean_ko}.gz" "$target_backup"
                else
                    cp "$clean_ko" "$target_backup"
                fi
                echo "$KVER" > "$BACKUP_DIR/${MODULE}.kver"
                echo "$target_orig" > "$BACKUP_DIR/${MODULE}.path"
                info "Successfully built clean unpatched driver!"
            fi
        fi
    fi

    if [ ! -f "$target_backup" ]; then
        die "No backup found at: $target_backup" \
            "\n         Automatic recovery of stock driver failed." \
            "\n         To manually restore stock driver, run: sudo apt install --reinstall linux-modules-extra-$(uname -r)"
    fi
}

# ==============================================================================
# Restore original module
# ==============================================================================

cmd_restore()
{
    echo -e "\n${BOLD}=== Restoring original module: ${MODULE} ===${NC}\n"

    local orig_path=""
    if [ -f "$BACKUP_DIR/${MODULE}.path" ]; then
        orig_path=$(cat "$BACKUP_DIR/${MODULE}.path")
    else
        orig_path=$(modinfo -F filename "$MODULE" 2>/dev/null || echo "")
        if [ -z "$orig_path" ]; then
            orig_path=$(find "/lib/modules/${KVER}" \( -name "${MODULE}.ko*" -o -name "${MOD_FILESTEM}.ko*" \) 2>/dev/null | head -n 1 || echo "")
        fi
    fi

    if [ -z "$orig_path" ]; then
        die "Cannot find module path for $MODULE"
    fi

    local backup_file="$BACKUP_DIR/$(basename "$orig_path").orig"

    if [ ! -f "$backup_file" ]; then
        recover_stock_module "$backup_file" "$orig_path"
    fi

    if [ -f "$BACKUP_DIR/${MODULE}.kver" ]; then
        local backup_kver
        backup_kver=$(cat "$BACKUP_DIR/${MODULE}.kver")
        if [ "$backup_kver" != "$KVER" ]; then
            warn "Backup was made for kernel ${backup_kver}, current is ${KVER}"
            if ! $AUTO_CONFIRM; then
                read -rp "  Continue anyway? [y/N] " reply
                if [[ ! "${reply:-}" =~ ^[Yy]$ ]]; then
                    exit 0
                fi
            fi
        fi
    fi

    # Unload module safely from RAM
    unload_module_safely "$MODULE"

    # Restore original file to disk
    info "Restoring original module file to $orig_path ..."
    cp "$backup_file" "$orig_path"
    depmod -a "$KVER"

    # Reload original module
    info "Loading original module into kernel RAM ..."
    if modprobe "$MODULE"; then
        info "Original module loaded successfully!"
    else
        die "Failed to load original module"
    fi

    # Verify that disable_dtr_rts parameter is GONE
    if [ ! -f "/sys/module/${MODULE}/parameters/disable_dtr_rts" ]; then
        info "CONFIRMED: Original Ubuntu driver is ACTIVE in kernel RAM!"
    else
        warn "Warning: disable_dtr_rts parameter still present in sysfs."
    fi

    # Clean up backup files
    rm -f "$backup_file" "$BACKUP_DIR/${MODULE}.kver" "$BACKUP_DIR/${MODULE}.path" 2>/dev/null || true
    rmdir "$BACKUP_DIR" 2>/dev/null || true

    # Clean up udev rule if no other patched drivers exist
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        rm -f /etc/udev/rules.d/99-kernel-uart-patcher.rules 2>/dev/null || true
        udevadm control --reload-rules 2>/dev/null || true
    fi

    # Rebind devices
    rebind_devices "$MODULE"

    echo ""
    echo -e "  ${GREEN}${BOLD}✓ Original Ubuntu driver restored 100%!${NC}"
    echo ""
}

cmd_toggle()
{
    local val="${1:-}"
    if [ -z "$val" ]; then
        die "Usage: sudo ./$SCRIPT_NAME toggle <module> <0|1|on|off>"
    fi

    local param_path="/sys/module/${MODULE}/parameters/disable_dtr_rts"

    if [ ! -f "$param_path" ]; then
        die "Module $MODULE does not have parameter disable_dtr_rts." \
            "\n         You must run 'sudo ./$SCRIPT_NAME patch $MODULE' first."
    fi

    case "$val" in
        1|on|true|yes|enable)
            echo "Y" > "$param_path"
            chmod 0666 "$param_path" 2>/dev/null || true
            info "DTR/RTS control is now DISABLED (pins forced HIGH, Gimbal will NOT reset)"
            ;;
        0|off|false|no|disable)
            echo "N" > "$param_path"
            chmod 0666 "$param_path" 2>/dev/null || true
            info "DTR/RTS control is now ENABLED (default Linux kernel behavior restored)"
            ;;
        *)
            die "Invalid toggle value: $val (use 1/on or 0/off)"
            ;;
    esac
}

cmd_status()
{
    echo -e "\n${BOLD}=== UART Kernel Module Status ===${NC}\n"

    echo -e "  ${CYAN}Kernel:${NC}      $KVER"

    local sb_state="unknown"
    if command -v mokutil &>/dev/null; then
        sb_state=$(mokutil --sb-state 2>/dev/null | head -1 || echo "unknown")
    fi
    echo -e "  ${CYAN}Secure Boot:${NC} $sb_state"

    local headers_ok="no"
    [ -d "/lib/modules/${KVER}/build" ] && headers_ok="yes"
    echo -e "  ${CYAN}Headers:${NC}     $headers_ok"

    echo ""
    echo -e "  ${CYAN}USB Serial Drivers:${NC}"

    for mod in cp210x ch341 ftdi_sio pl2303 cdc_acm; do
        local status="${RED}not loaded${NC}"
        local param_info=""

        if [ -d "/sys/module/${mod}" ]; then
            status="${GREEN}loaded${NC}"
            local pfile="/sys/module/${mod}/parameters/disable_dtr_rts"
            if [ -f "$pfile" ]; then
                local pval
                pval=$(cat "$pfile" 2>/dev/null || echo "?")
                if [ "$pval" = "Y" ] || [ "$pval" = "1" ]; then
                    param_info=" ${GREEN}(DEEP PATCHED: disable_dtr_rts = ON)${NC}"
                else
                    param_info=" ${YELLOW}(DEEP PATCHED: disable_dtr_rts = OFF)${NC}"
                fi
            elif [ -f "$BACKUP_DIR/${mod}.kver" ]; then
                param_info=" ${YELLOW}(backup exists)${NC}"
            fi
        fi

        printf "    %-12s %b%b\n" "$mod" "$status" "$param_info"
    done

    echo ""
    echo -e "  ${CYAN}Connected Serial Ports:${NC}"

    local found_port=false
    for port in /dev/ttyUSB* /dev/ttyACM*; do
        [ -e "$port" ] || continue
        found_port=true
        local port_name
        port_name=$(basename "$port")
        local driver="unknown"
        local mod_link="/sys/class/tty/${port_name}/device/driver/module"
        if [ -L "$mod_link" ]; then
            driver=$(basename "$(readlink -f "$mod_link")")
        fi
        echo -e "    ${BOLD}${port}${NC} → driver: ${CYAN}${driver}${NC}"
    done

    if ! $found_port; then
        echo "    (no serial devices detected)"
    fi

    echo ""
}

# ==============================================================================
# Usage
# ==============================================================================

usage()
{
    echo ""
    echo -e "${BOLD}uart_kernel_patch.sh${NC} — Deep Patch for USB Serial Drivers (Disable DTR/RTS)"
    echo ""
    echo -e "${BOLD}Usage:${NC}"
    echo "  sudo ./$SCRIPT_NAME patch   <port|module> [-y]       Deep patch driver, neutralize DTR/RTS"
    echo "  sudo ./$SCRIPT_NAME restore <port|module> [-y]       Restore original Ubuntu driver"
    echo "  sudo ./$SCRIPT_NAME toggle  <port|module> <1|0>      Live toggle without reloading module"
    echo "       ./$SCRIPT_NAME status                           Show driver & port status"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  sudo ./$SCRIPT_NAME patch   cp210x                   # Patch Silicon Labs CP210x"
    echo "  sudo ./$SCRIPT_NAME patch   /dev/ttyUSB0             # Auto-detect driver from port"
    echo "  sudo ./$SCRIPT_NAME toggle  cp210x 0                 # Live restore kernel default"
    echo "  sudo ./$SCRIPT_NAME toggle  cp210x 1                 # Live disable DTR/RTS"
    echo "  sudo ./$SCRIPT_NAME restore cp210x                   # Restore original .ko file"
    echo "  ./$SCRIPT_NAME status                                # Check current status"
    echo ""
}

# ==============================================================================
# Main
# ==============================================================================

main()
{
    if [ $# -lt 1 ]; then
        usage
        exit 1
    fi

    local cmd="$1"
    shift

    local target=""
    local extra_arg=""
    while [ $# -gt 0 ]; do
        case "$1" in
            -y|--yes)
                AUTO_CONFIRM=true
                ;;
            *)
                if [ -z "$target" ]; then
                    target="$1"
                elif [ -z "$extra_arg" ]; then
                    extra_arg="$1"
                fi
                ;;
        esac
        shift
    done

    case "$cmd" in
        patch)
            [ -z "$target" ] && { usage; die "Missing <port|module> argument"; }
            [ "$(id -u)" -ne 0 ] && die "Must run as root. Use: sudo ./$SCRIPT_NAME patch $target"
            resolve_module "$target"
            info "Target module: ${MODULE} (${MOD_FILESTEM})"
            cmd_patch
            ;;
        restore)
            [ -z "$target" ] && { usage; die "Missing <port|module> argument"; }
            [ "$(id -u)" -ne 0 ] && die "Must run as root. Use: sudo ./$SCRIPT_NAME restore $target"
            resolve_module "$target"
            cmd_restore
            ;;
        toggle)
            [ -z "$target" ] || [ -z "$extra_arg" ] && { usage; die "Usage: sudo ./$SCRIPT_NAME toggle <module> <1|0>"; }
            [ "$(id -u)" -ne 0 ] && die "Must run as root. Use: sudo ./$SCRIPT_NAME toggle $target $extra_arg"
            resolve_module "$target"
            cmd_toggle "$extra_arg"
            ;;
        status)
            cmd_status
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage
            die "Unknown command: $cmd"
            ;;
    esac
}

main "$@"
