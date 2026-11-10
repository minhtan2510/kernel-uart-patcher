# AGENT.md — Operating Guidelines for AI Assistants

This document provides essential instructions, architectural boundaries, coding conventions, and operational workflows for any AI coding assistant working on the **Linux Serial Patcher** (`LinuxUART`) repository.

---

## 1. Project Purpose & Scope

The **Linux Serial Patcher** repository provides a reliable, kernel-level solution to prevent Ubuntu Linux and userspace applications from asserting `DTR`/`RTS` (pulling them LOW / 0V) when opening serial ports. This prevents connected hardware (such as Gremsy gimbals, STM32, ESP32, and Arduino boards) from experiencing unwanted resets triggered through hardware `RESET`/`NRST` lines.

---

## 2. Directory Layout & Invariance Rules

```text
LinuxUART/
├── run.sh                       # SOLE EXECUTABLE in root directory (GUI launcher)
├── README.md                    # User-facing documentation
├── MEMORY.md                    # Long-term architectural context & ADRs
├── AGENT.md                     # Agent operational handbook (this file)
├── .gitignore
└── src/
    ├── core/                    # CORE DRIVER ENGINE (CRITICAL - DO NOT ALTER UNLESS ASKED)
    │   ├── patch_driver.py      # 5-layer deep patch code transformer
    │   └── uart_kernel_patch.sh # Kernel build, out-of-tree install, safe unbind
    └── gui/                     # USER INTERFACE
        └── gui.py               # Ultra-compact modern minimalist Tkinter widget
```

### Critical Invariance Rules:
1. **Core Protection**: Files in [`src/core/`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core) have been tested and verified on actual hardware. **Do not modify [`src/core/uart_kernel_patch.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/uart_kernel_patch.sh) or [`src/core/patch_driver.py`](file:///home/minhtan/Desktop/Script/LinuxUART/src/core/patch_driver.py)** unless the user explicitly requests changes to core logic.
2. **Single Root Executable**: The repository root must contain **only one runnable script**: [`run.sh`](file:///home/minhtan/Desktop/Script/LinuxUART/run.sh). Any additional internal scripts or modules must be placed in appropriate subfolders under `src/`.
3. **Preserve User Intent & Git History**: Use `git mv` when restructuring files to maintain complete commit history.

---

## 3. Communication & Code Standards

Follow these rules at all times:

### Language
- **User Explanations**: Vietnamese (`Tiếng Việt`).
- **Code & Identifiers**: English.
- **Code Comments**: English.
- **Doxygen Documentation**: English (`@brief`, `@param`, `@return`).

### Code Style
- **C/C++**: BSD/Allman style formatting (opening brace `{` on its own line for functions, control structures, and blocks).
- **Python**: Clean PEP8 standards, Allman-like block separation, type hints where helpful, and standard library only for GUI (no third-party pip dependencies like PyQt or PySide).
- **GUI Styling**: Modern Minimalist (Tailwind Slate/Zinc Dark Mode palette: `#090D16`, `#111726`, `#1E293B`, `#10B981`, `#2563EB`).

---

## 4. Workflows & Command Reference

### Launching the Application
```bash
# User launch command
./run.sh
```

### Direct CLI Core Operations
```bash
# Check status of installed patches and active driver parameters
sudo ./src/core/uart_kernel_patch.sh status

# Patch cp210x driver (locks DTR/RTS High)
sudo ./src/core/uart_kernel_patch.sh patch cp210x -y

# Live toggle protection without reloading driver (1 = Shield Active, 0 = Inactive)
sudo ./src/core/uart_kernel_patch.sh toggle cp210x 1
sudo ./src/core/uart_kernel_patch.sh toggle cp210x 0

# Restore factory stock driver
sudo ./src/core/uart_kernel_patch.sh restore cp210x -y
```

### Automated Verification Workflows
When modifying UI or launcher code, verify without hanging:
```bash
# 1. Shell syntax check
bash -n run.sh
bash -n src/core/uart_kernel_patch.sh

# 2. Python syntax compilation
python3 -m py_compile src/gui/gui.py
python3 -m py_compile src/core/patch_driver.py

# 3. Headless GUI initialization test
python3 -c "import tkinter as tk, sys; sys.path.insert(0, 'src/gui'); import gui; r = tk.Tk(); app = gui.UARTShieldApp(r); r.update(); r.destroy()"
```

---

## 5. Technical Context & Gotchas

1. **Root Elevation**:
   - The GUI runs with regular user privileges and elevates operations on-demand via `pkexec` when calling `src/core/uart_kernel_patch.sh`.
   - Never run `python3 src/gui/gui.py` directly with `sudo` (running Tkinter as root breaks X11 authority and Wayland permissions).
2. **Device Unbinding Quirks**:
   - `rmmod` will fail if the USB adapter is active. `unload_module_safely()` in `uart_kernel_patch.sh` automatically unbinds active USB interfaces before module removal.
   - If `rmmod` still reports in use, a userspace process has `/dev/ttyUSB*` open. Identify via `fuser /dev/ttyUSB*` or `lsof /dev/ttyUSB*`.
3. **Typography Resolution**:
   - The GUI uses `resolve_best_font()` to dynamically cascade fonts (`Google Sans` → `SF Pro Display` → `Ubuntu` → `Inter`). Do not hardcode a single font family without fallback.

