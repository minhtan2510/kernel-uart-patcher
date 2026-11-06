# Kernel UART Patcher

> **Linux DTR/RTS Reset Shield & Control Panel**  
> Prevent unwanted MCU, gimbal, and development board reboots caused by serial connections on Linux.

---

## Overview

When opening a serial port on Linux, the kernel and userspace libraries (PySerial, QtSerialPort, ROS, gimbal tools) automatically assert **DTR/RTS** lines (pulling them LOW / 0V). On microcontrollers (STM32, ESP32, Arduino) and drone gimbals (Gremsy), `DTR` is hardwired to the hardware `RESET`/`NRST` pin, triggering continuous device reboots upon connect.

**Kernel UART Patcher** solves this at the kernel level by applying an out-of-tree **Deep Patch** to Linux serial drivers. It exposes a live runtime parameter (`disable_dtr_rts`) under `/sys/module/<driver>/parameters/`, allowing you to lock reset pins HIGH (3.3V) with 1 click without reconnecting USB or recompiling.

---

## Highlights

- **Standalone Single Binary**: 55 MB self-contained ELF executable (`Kernel UART Patcher`). Zero setup required — runs on any Ubuntu/Debian system without pre-installed Python or PyQt6.
- **System Tray Companion**: Minimizes silently to system tray. Features right-click quick toggle (**Block Reset Pins**) and HiDPI status glyphs (`✓` Active, `—` Inactive).
- **Ultra-Low Overhead**: 0 subprocess spawns in background, 0.00% idle CPU utilization, and sub-millisecond hardware scans via pure Linux sysfs/udev cache.
- **Live On/Off Toggle**: Switch between **Protected Mode** (DTR held HIGH) and **Flash/Bootloader Mode** (DTR asserts normally) instantly.
- **Safe Kernel Module Lifecycle**: Clean unbind/bind, local driver backups (`/var/backups/uart_dtr_patch`), and one-click restore to official Ubuntu stock driver.

---

## Quick Start

### 1. Run Standalone Executable (Recommended)
Simply double-click **`Kernel UART Patcher`** or run from terminal:
```bash
./"Kernel UART Patcher"
```

### 2. Run from Source (Development)
```bash
./scripts/run.sh
```

### 3. Rebuild Executable
```bash
./scripts/build.sh
```

### 4. Headless CLI Usage
For automated CI or headless servers without a desktop display:
```bash
# Patch and install driver for connected adapter (e.g. cp210x, ftdi_sio)
sudo ./src/core/uart_kernel_patch.sh patch cp210x

# Enable reset protection (DTR held HIGH)
sudo ./src/core/uart_kernel_patch.sh toggle cp210x 1

# Disable reset protection (allow bootloader flashing)
sudo ./src/core/uart_kernel_patch.sh toggle cp210x 0

# Restore original Ubuntu factory driver
sudo ./src/core/uart_kernel_patch.sh restore cp210x
```

---

## Project Structure

```text
LinuxUART/
├── Kernel UART Patcher       # Standalone executable binary (zero dependencies)
├── README.md                 # Project documentation
├── MEMORY.md                 # Architecture Decision Records & persistent memory
├── AGENT.md                  # AI pair-programming context & hardware rules
├── .gitignore                # Git ignore rules
├── scripts/                  # Development & build automation
│   ├── run.sh                # Launch GUI from Python source
│   └── build.sh              # Package into standalone ELF binary via PyInstaller
└── src/                      # Source code
    ├── core/                 # Kernel patch engine (uart_kernel_patch.sh, patch_driver.py)
    └── gui/                  # Modern PyQt6 control panel & tray companion (gui.py)
```

---

## Supported Hardware Adapters

| Chipset | Kernel Module | Common Devices |
| :--- | :--- | :--- |
| **Silicon Labs** | `cp210x` | CP2102, CP2102N, CP2104, NodeMCU, ESP32 DevKit |
| **FTDI** | `ftdi_sio` | FT232R, FT232H, FT2232H, Gremsy Gimbals, Pixhawk |
| **WCH** | `ch341` | CH340G, CH340C, CH341A, Arduino Nano clones |
| **Prolific** | `pl2303` | PL2303HX, PL2303TA, industrial serial converters |
| **USB CDC ACM** | `cdc_acm` | Native USB serial gadgets, STM32 VCP, Teensy, Raspberry Pi Pico |

---

## How the Deep Patch Works

Standard userspace `termios` flags (`CLOCAL`, `~HUPCL`) fail because the Linux kernel triggers the driver's `.dtr_rts()` callback during `tty_port_open()` before userspace gains control.

The **5-Layer Deep Patch** intervenes directly inside the kernel driver:
1. **Module Parameter**: Exposes `/sys/module/<driver>/parameters/disable_dtr_rts` for dynamic control.
2. **Port Open Interception**: Commands adapter hardware to lock DTR/RTS HIGH immediately upon port initialization.
3. **IOCTL Filter**: Intercepts `ioctl(TIOCMSET)` to strip `TIOCM_DTR` and `TIOCM_RTS` bits from userspace requests.
4. **Kernel Callback Override**: Neutralizes `.dtr_rts()` driver callbacks.
5. **Flow Control Safeguard**: Prevents `set_termios` from re-asserting modem control lines.

---

## License

GPL-2.0 / MIT
