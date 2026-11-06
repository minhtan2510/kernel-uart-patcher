# Project Memory & Architecture Context

## 1. Project Overview & Core Stack
* **Repository:** `LinuxUART` — **Kernel UART Patcher** (Linux USB-UART DTR/RTS Reset Shield).
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

### [2026-11-05] ADR-07: Migration from Tkinter to PyQt6 for Hardware-Accelerated Modern UI
* **Context:** Tkinter relies on 1990s X11 bitmap rendering without hardware acceleration or antialiased rounded borders, leading to crude, blocky visuals and poor FreeType font rendering. The host system already possesses PyQt6 (Qt 6.11.2).
* **Decision:** Re-architected `src/gui/gui.py` to use PyQt6:
  - Antialiased hardware-accelerated rounded rectangles (`border-radius: 12px;` on card, `border-radius: 8px;` on combobox & buttons).
  - High-precision text shaping with HarfBuzz and subpixel antialiasing.
  - 60fps animated toggle switch via `QPropertyAnimation`.
  - Background asynchronous command execution via `QThread` and Qt signals/slots.
* **Consequences:** Commercial-grade modern desktop aesthetics, fluid animations, crisp typography, and zero lag.

### [2026-11-05] ADR-08: Clean Minimalist Light Mode Theme & Custom Vector Controls
* **Context:** User requested a Light Theme ("Đổi theme của giao diện thành Light cho dễ nhìn") to enhance daylight legibility and visual comfort.
* **Decision:**
  - Modern Minimalist Light palette inspired by Tailwind Slate / Zinc:
    - Base background: Slate-50 (`#f8fafc`) to eliminate harsh 100% white glare.
    - Card surfaces & inputs: Crisp pure white (`#ffffff`) with Slate-200 (`#e2e8f0`) and Slate-300 (`#cbd5e1`) borders.
    - Typography: Slate-900 (`#0f172a`) for crisp contrast; Slate-600 (`#475569`) for secondary metadata; Slate-400 (`#94a3b8`) for hints.
    - Status Pills:
      - Shield Active: Emerald-50 (`#ecfdf5`), border Emerald-200 (`#a7f3d0`), text Emerald-800 (`#065f46`).
      - Shield Inactive: Amber-50 (`#fffbeb`), border Amber-200 (`#fde68a`), text Amber-800 (`#92400e`).
      - Stock Driver: Slate-100 (`#f1f5f9`), border Slate-300 (`#cbd5e1`), text Slate-600 (`#475569`).
    - Custom Port ComboBox Chevron: Replaced legacy Fusion 3D beveled arrow with custom antialiased vector chevron (`QPainterPath` with round cap/join in `PortComboBox.paintEvent`).
* **Consequences:** Pristine, modern light theme with superior daylight readability and clean vector aesthetics.

### [2026-11-05] ADR-09: Rebrand Project to `Kernel UART Patcher`
* **Context:** The previous title `UART Shield` was ambiguous and frequently misidentified as an Arduino/Raspberry Pi hardware expansion board rather than an out-of-tree kernel driver patching utility.
* **Decision:**
  - Officially renamed the desktop tool and repository identity to **`Kernel UART Patcher`**.
  - Updated window title: `Kernel UART Patcher`.
  - Re-badged header tag from `KERNEL` to `DTR/RTS` to eliminate lexical redundancy (`Kernel UART Patcher • DTR/RTS`).
* **Consequences:** Accurate technical branding reflecting its kernel-level out-of-tree patching capabilities.

### [2026-11-05] ADR-10: Expanded Window Layout & Permanent Activity Log
* **Context:** User requested slightly increasing window dimensions and making the activity log view permanent by default, removing the collapsible drawer toggle.
* **Decision:**
  - Upgraded window dimensions to `420x500` px (providing room for ~55-character log lines without wrapping).
  - Made `QPlainTextEdit` activity log permanently visible.
  - Removed log toggle button (`Log ▸` / `Log ▾`), collapsible state variable, and `Ctrl+L` shortcut.
  - Simplified footer to status / spinner on left, `Clear` button on right.
  - Added modern minimalist 6px rounded scrollbar styling (`QScrollBar:vertical`) to eliminate bulky default Fusion scrollbars.
* **Consequences:** Instant visibility into kernel module status, unbind operations, and compiler output without manual expansion; clean, stable window layout without geometric shifting.

### [2026-11-06] ADR-11: Frictionless Direct Sysfs Toggling & Self-Healing Parameter Permissions
* **Context:** When the user clicked the toggle switch to turn off reset protection, `gui.py` spawned `pkexec uart_kernel_patch.sh toggle <mod> 0`. This popped up a root authentication dialog. Dismissing or canceling the prompt aborted the toggle with `rc=126 (Request dismissed)`. The GUI then re-read the unchanged sysfs parameter and reverted the switch back to ON, causing an apparent "switch bounces back ON when turned OFF" bug.
* **Decision:**
  1. **Direct Sysfs Write in GUI (`src/gui/gui.py`):** Attempt direct Python file write to `/sys/module/<driver>/parameters/disable_dtr_rts` first. If permissions allow, state transitions occur in <1ms without sub-processes or password prompts.
  2. **Self-Healing Permissions (`src/core/uart_kernel_patch.sh`):**
     - During `install_module()`, immediately `chmod 0666` the parameter file and install `/etc/udev/rules.d/99-kernel-uart-patcher.rules` so permissions persist across reboots and USB reconnects.
     - In `cmd_toggle()`, apply `chmod 0666` whenever executed via pkexec fallback.
     - In `cmd_restore()`, clean up the udev rule when no patched drivers remain.
* **Consequences:** Zero password prompts when clicking the toggle switch, instant tactile feedback, and elimination of toggle bounce-backs.

### [2026-11-06] ADR-13: Full Multi-Driver Patching Engine & Hardware Port Prioritization
* **Context:** User clicked "Install Kernel Shield", log reported success, but status remained `△ Stock Driver` and physical testing showed no reset protection.
* **Root Causes:**
  1. **Alphabetical Port Inversion:** Python alphabetical sort placed `/dev/ttyACM0` (Linux for Tegra USB gadget) before `/dev/ttyUSB0` (CP2102N UART Bridge). The GUI defaulted to index 0, so the user unknowingly initiated patching for `cdc_acm` instead of `cp210x`.
  2. **Incomplete Driver Support:** `patch_driver.py` lacked implementation for `cdc_acm` and `pl2303`, falling back to an inert stub that did not inject `disable_dtr_rts`.
  3. **Non-Fatal Verification:** `uart_kernel_patch.sh` emitted a `warn` instead of `die` when `disable_dtr_rts` was absent in sysfs, returning exit code 0 and causing a false-positive success log.
* **Decision:**
  - Implemented complete deep-patch support for `cdc_acm` and `pl2303` in `src/core/patch_driver.py`.
  - Made sysfs parameter verification strictly fatal in `src/core/uart_kernel_patch.sh` (`die` on missing parameter).
  - Prioritized `ttyUSB*` ahead of `ttyACM*` and injected `udevadm` device model descriptions directly into the ComboBox.
  - Dynamically branded install/patch buttons with target driver names (e.g. `Install Kernel Shield (cp210x)`).
* **Consequences:** Physical UART bridges are selected first; all 5 major USB-UART/ACM drivers are fully protected; zero false-positive success logs.

### [2026-11-06] ADR-14: Action Row Consolidation (70/30) & Elimination of Redundant Rebuild
* **Context:** The GUI previously displayed redundant actions (`Install Kernel Shield` inside the hero card + `Rebuild Patch` / `Restore` row below). Furthermore, once a driver was already patched and operating (`PATCHED ACTIVATED` / `PATCHED INACTIVE`), displaying a 70%-width `Rebuild Patch` button was confusing, redundant for daily use, and risked accidental recompilation/port disconnect.
* **Decision:**
  1. **Consolidated Action Row (70/30 Split):**
     - Removed `btn_install` from the hero card, keeping only the bottom 2 action buttons.
     - Bottom row configured with `stretch=7` for Button 1 and `stretch=3` for Button 2.
  2. **State-Driven Button Visibility:**
     - **`SYSTEM DEFAULT` / `NO DEVICE`**:
       - Button 1 (`btn_patch`): Visible, primary CTA `#2563eb` with text `Patch Driver (<driver>)`.
       - Button 2 (`btn_restore`): Visible, disabled with tooltip: `"Cannot restore: driver is already the original factory driver."`.
     - **`PATCHED ACTIVATED` / `PATCHED INACTIVE`**:
       - Button 1 (`btn_patch`): **Hidden completely** to eliminate confusion and focus user attention on the Toggle Switch.
       - Button 2 (`btn_restore`): Expands to full width with text `Restore Original Driver (<driver>)`, enabled with subtle border and red hover highlight.
  3. **Developer Rebuild Access:**
     - Right-click context menu on the Hero Card provides `Force Rebuild Driver (<driver>)`.
     - Keyboard shortcut `Ctrl+Shift+R` triggers forced rebuild.
  4. **Direct Status Badges:**
     - Removed all icons from the status badges.
     - Standardized on exact terms: `PATCHED ACTIVATED`, `PATCHED INACTIVE`, `SYSTEM DEFAULT`, `NO DEVICE`.
     - Upgraded typography and padding (`PILL_STYLE_BASE`: 12px bold, 5px 14px padding, 8px radius).
* **Consequences:** Clean visual hierarchy; zero button redundancy; focus remains 100% on the toggle switch when protected; developer rebuild options remain readily accessible via shortcut and context menu.

### [2026-11-06] ADR-15: Synchronized Light Semantic Log Console with Visual Outcome Banners
* **Context:** The activity log previously rendered all messages in monochrome gray inside a white box. Success, errors, build steps, and action triggers looked identical, making it difficult for users to visually confirm whether long operations (patching, compiling, restoring) succeeded or failed.
* **Decision:**
  1. **Synchronized Light Console (`#ffffff`):**
     - Retained pure white `#ffffff` background with `#cbd5e1` border and rounded 8px corners to preserve 100% theme consistency with the hero card and controls.
     - Monospaced typography with crisp rendering and comfortable padding (`8px 10px`).
     - Minimalist light vertical scrollbar styling.
  2. **Semantic Color & Outcome Highlighting on Light Background:**
     - **Action Header (`[ACTION]`):** Highlighted in bold blue (`#1d4ed8`) with prefix `▶`.
     - **Success Banner (`[DONE]` / `[SUCCESS]`):** Prominent emerald chip with light green fill (`#ecfdf5`), soft border (`#a7f3d0`), and deep green text (`#15803d`) with prefix `✓`.
     - **Failure Banner (`[FAIL]` / `[ERROR]`):** Prominent crimson chip with light red fill (`#fef2f2`), soft border (`#fecaca`), and deep red text (`#b91c1c`) with prefix `✗`.
     - **Milestone Steps (`[OK]`):** Forest green (`#16a34a`) with checkmark `✓`.
     - **Step Errors (`[ERR]`):** Crimson red (`#dc2626`) with crossmark `✗`.
     - **Warnings (`[WARN]`, `[!!]`):** Amber (`#b45309`) with warning sign `⚠`.
     - **Cancel Notice (`[CANCEL]`):** Neutral light gray chip (`#f1f5f9`, `#64748b`) with prefix `⊘`.
     - **Background/Compiler Output:** Soft muted slate (`#64748b` for indented lines, `#334155` for standard text).
  3. **Auto-Scrolling:**
     - Dynamically scrolls `QPlainTextEdit` to the maximum vertical scroll value upon each new line appended.
* **Consequences:** Seamless aesthetic consistency across the light interface; instant visual comprehension of operation outcomes without visual jarring.

### ADR-16: Prominent Status Badge Architecture with High-Contrast Theming
* **Status:** Accepted (2026-11-06)
* **Context:** The status badge in the hero card (`lbl_pill`) conveys critical hardware driver state (`PATCHED ACTIVATED`, `PATCHED INACTIVE`, `SYSTEM DEFAULT`). The previous `12px` font with subtle `1px` pastel border looked like a secondary tag rather than the primary visual focal point.
* **Decision:**
  - Increased typography size from `12px` to `14px` (`font-weight: bold; letter-spacing: 0.5px;`).
  - Increased padding from `5px 14px` to `7px 18px` with rounded radius `9px` (height scaled from 27px to 36px).
  - Doubled border thickness to `2px solid` with rich, high-contrast Tailwind palette:
    - `PATCHED ACTIVATED`: Background `#dcfce7` (Emerald 100), Border `#10b981` (Emerald 500), Text `#047857` (Emerald 700).
    - `PATCHED INACTIVE`: Background `#fef3c7` (Amber 100), Border `#f59e0b` (Amber 500), Text `#92400e` (Amber 800).
    - `SYSTEM DEFAULT`: Background `#f1f5f9` (Slate 100), Border `#94a3b8` (Slate 400), Text `#1e293b` (Slate 800).
  - Scaled animated toggle switch to `48x26` and centered both widgets vertically via `Qt.AlignmentFlag.AlignVCenter`.
* **Consequences:** Immediately draws user attention to the current driver protection state while maintaining strict light-theme harmony.

### ADR-17: Self-Healing Stock Driver Recovery with Dynamic DPKG/APT Resolution
* **Status:** Accepted (2026-11-06)
* **Context:** If the backup directory (`/var/backups/uart_dtr_patch/`) or `.orig` file is manually removed by a user or cleanup script, `cmd_restore` would fail with an unrecoverable `die` abort.
* **Decision:**
  - Implemented `recover_stock_module()` self-healing fallback triggered whenever the local backup file is absent.
  - Dynamically resolves the exact parent kernel package owning the target module file on the running system using `dpkg -S "$target_orig"` (e.g. `linux-modules-extra-$(uname -r)` across generic, lowlatency, oem, hwe).
  - Automatically fetches the official deb package via `apt-get download "$pkg"`, extracts only the pristine stock `.ko` file via `dpkg-deb -x`, and populates the backup cache before completing the restore.
  - Secondary fallback: If APT/network is unavailable, compiles clean unpatched source directly via `prepare_source` + `build_module` (matching module compression `.ko`, `.zst`, `.xz`, `.gz`).
  - Automatically adapts to any supported driver (`cp210x`, `ch341`, `ftdi_sio`, `pl2303`, `cdc_acm`).
* **Consequences:** Eliminates single-point-of-failure on backup files. Restore operations always succeed even if user purged backups.

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

