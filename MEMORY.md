# Project Memory & Architecture Context

## 1. Project Overview & Core Stack
* **Repository:** `LinuxUART` — Linux USB-UART DTR/RTS Reset Shield.
* **Core Problem:** Linux kernel and userspace serial libraries (PySerial, QtSerialPort, Gimbal GUIs) automatically assert `DTR`/`RTS` (driving them LOW / 0V) on connect. On gimbals (Gremsy) and microcontrollers (STM32, ESP32, Arduino), `DTR` is hardwired to the MCU hardware `NRST`/`RESET` line, causing continuous resets upon connection.
* **Architecture:**
  - **Single Entry Point:** [`run.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/run.sh) in root directory.
  - **Core Layer ([`src/core/`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core)):** Out-of-tree kernel driver deep-patching engine ([`patch_driver.py`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/patch_driver.py), [`uart_kernel_patch.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/uart_kernel_patch.sh)).
  - **GUI Layer ([`src/gui/`](file:///home/minhtan/Desktop/Script/LinuxUART/src/gui)):** Python 3 Tkinter/ttk ultra-compact modern minimalist control widget ([`gui.py`](file:///home/minhtan/Desktop/Script/LinuxUART/src/gui/gui.py)).

---

## 2. Key Architectural Decisions (ADR)

### [2026-11-05] ADR-01: Deep Kernel Driver Patching vs Userspace `termios`
* **Context:** Initial userspace attempts using C `termios` (`CLOCAL`, `~HUPCL`, `ioctl(TIOCMBIC)`) failed to prevent Gimbal resets.
* **Root Cause:**
  1. Kernel `tty_port_open()` triggers the driver's `.dtr_rts()` callback before userspace gains control.
  2. Userspace libraries explicitly invoke `ioctl(TIOCMSET)` / `ioctl(TIOCMBIS)` with `TIOCM_DTR`, which triggers `.tiocmset` in the driver and pulls `DTR` low.
  3. `CP210X_IFC_ENABLE` during interface initialization defaults modem control pins to active low unless explicitly commanded.
* **Decision:** Implement a 5-layer Deep Patch in the kernel driver:
  - **Layer 1 (Runtime Parameter):** Expose `disable_dtr_rts` in `/sys/module/<mod>/parameters/` for live on/off toggling without recompiling.
  - **Layer 2 (Port Open):** Issue hardware command `CP210X_SET_MHS` with mask `0x0300` immediately upon opening to lock DTR/RTS HIGH (3.3V).
  - **Layer 3 (IOCTL Interception):** Filter out `TIOCM_DTR` and `TIOCM_RTS` from `set` bitmask in `tiocmset_port()`.
  - **Layer 4 (Kernel Callback):** Override `.dtr_rts` callback to unconditionally force pins inactive.
  - **Layer 5 (Flow Control):** Ensure `set_termios` cannot re-assert DTR.
* **Consequences:** 100% immune to userspace app behavior; Gimbal stays online without resetting.

### [2026-11-05] ADR-02: Out-of-Tree Dynamic Build for Ubuntu HWE Kernels
* **Context:** Ubuntu 22.04 LTS running HWE kernel 6.8 does not have `linux-source-6.8` in standard apt repositories (only `linux-source-5.15`).
* **Decision:** [`uart_kernel_patch.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/uart_kernel_patch.sh) dynamically downloads the official driver source from `git.kernel.org` matching the major kernel version, patches it via [`patch_driver.py`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/patch_driver.py), and builds against installed `linux-headers-$(uname -r)`.
* **Output Path:** Installed to `/lib/modules/$(uname -r)/updates/` with higher loading priority than factory `/lib/modules/$(uname -r)/kernel/drivers/usb/serial/`.

### [2026-11-05] ADR-03: Safe Module Unloading Mechanism
* **Context:** `rmmod cp210x` frequently failed with `rmmod: ERROR: Module cp210x is in use` while the USB device was physically plugged in.
* **Decision:** [`uart_kernel_patch.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/uart_kernel_patch.sh) implements `unload_module_safely()`:
  1. Searches `/sys/bus/usb/drivers/<mod>` and `/sys/bus/usb-serial/drivers/<mod>`.
  2. Unbinds each active interface via `echo "$dev" > unbind`.
  3. Verifies `refcnt == 0` in `/sys/module/<mod>/refcnt`.
  4. Unloads module cleanly via `rmmod`.

### [2026-11-05] ADR-04: Single Root Executable & Folder Organization
* **Context:** Root directory previously contained multiple loose scripts (`gui.py`, `run_gui.sh`, `uart_kernel_patch.sh`, `patch_driver.py`).
* **Decision:** Reorganized to:
  - Root: [`run.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/run.sh) (sole executable).
  - [`src/core/`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core): Internal driver patcher and kernel scripts.
  - [`src/gui/`](file:///home/minhtan/Desktop/Script/LinuxUART/src/gui): UI application.
* **Consequences:** Clean repository root, preserved Git history via `git mv`, zero path fragility.

### [2026-11-05] ADR-05: Ultra-Compact UI & Typography System
* **Context:** User requested a modern minimalist design that is as compact as possible and easy to read.
* **Decision:**
  - Window dimensions: `360x285` (collapsed), `360x435` (expanded with log).
  - Modern Dark palette: Slate 950 (`#090D16`), Card (`#111726`), Border (`#1E293B`).
  - Typography: `Google Sans` (UI) with fallback to `SF Pro Display` / `Ubuntu` / `Inter`, and `SF Mono` (Monospace) with fallback to `Fira Code` / `JetBrains Mono`.

### [2026-11-05] ADR-06: Modern Interactive Switch, Port Lock Warning & UX Polish
* **Context:** Binary runtime toggling via `toggle 0|1` was previously operated via a generic button, which did not cleanly convey binary on/off state, and port conflicts with background processes caused silent `rmmod` failures.
* **Decision:**
  - Implemented `ModernSwitch` (`tk.Canvas` pill toggle switch) for direct tactile on/off control of `disable_dtr_rts`.
  - Added `_check_port_lock()` using `fuser` to detect and display warning chips when a background process holds the port open.
  - Added danger hover state (`#ef4444`) to `Restore Stock` to protect against accidental downgrade.
  - Added in-button animated ASCII progress spinner during async `pkexec` operations.
  - Added keyboard shortcuts (`Space` to toggle, `Ctrl+R` to scan, `Ctrl+L` for logs, `Esc` to quit) and double-click to copy port.
* **Consequences:** Intuitive tactile control, zero accidental resets, and instant visibility into port locks.

---

## 3. Known Gotchas & Constraints

1. **Background Processes Holding Serial Ports:**
   - If an application (e.g. `./main`, `minicom`, `screen`) has an open file descriptor on `/dev/ttyUSB*`, `rmmod` will fail even after unbind. Check `fuser /dev/ttyUSB*` or `lsof /dev/ttyUSB*` if unbind hangs.
2. **`set -euo pipefail` in Bash:**
   - Do NOT pipe `lsmod | grep <module>` directly under `set -e` as `grep` returning non-zero causes immediate script termination. Instead check `[ -d "/sys/module/<mod>" ]`.
3. **Core Preservation Rule:**
   - Files in [`src/core/`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core) are tested, verified, and committed. Do NOT modify core logic unless explicitly authorized by the user.

---

## 4. Current Roadmap & Active Milestones
* [x] Core 5-layer deep patch for `cp210x` verified on hardware.
* [x] Safe unbind and automatic restore verified.
* [x] Ultra-compact minimalist GUI implemented with Tkinter (zero external dependencies).
* [x] Project reorganized with single root executable (`./run.sh`).
* [x] Typography upgraded to Google Sans + SF Mono.
* [ ] Support testing for additional USB-UART bridges (`ch341`, `ftdi_sio`, `pl2303`).

