# Kernel UART Patcher — User Guide

A lightweight Linux tool that prevents unwanted hardware resets on embedded devices (Gimbals, STM32, ESP32, Arduino) by suppressing DTR and RTS signal assertion during serial port connection.

---

## 1. Quick Start

### Prerequisites
- **OS**: Linux x86_64 (Ubuntu 20.04 / 22.04 / 24.04, Debian, Linux Mint, etc.)
- **Dependencies**: `build-essential` and `linux-headers-$(uname -r)` (automatically detected and prompted if missing).
- **Secure Boot**: Must be **Disabled** in BIOS/UEFI to allow loading custom-built kernel modules.

### Running the Application
Simply double-click the executable or run it from the terminal:
```bash
./"Kernel UART Patcher"
```

---

## 2. Core Features & Usage

### 2.1. Patching a Driver
1. Select your target device from the **Connected Serial Port** dropdown (e.g., `/dev/ttyUSB0 (ftdi_sio)`).
2. Click **Patch <driver>** (e.g., `Patch ftdi_sio`).
3. Enter your administrator (`sudo`) password when prompted.
4. Once completed, the badge will switch to **`PATCH ACTIVE` 🟢**. All user applications (PySerial, Minicom, ROS nodes, etc.) can now connect to this port without triggering a device reset.

### 2.2. Live Shield Toggle
- **PATCH ACTIVE (Green)**: DTR/RTS suppression is active. Hardware resets are blocked.
- **PATCH INACTIVE (Amber)**: Suppression is paused live via sysfs. Standard Linux behavior resumes (useful when you want to flash firmware).
- *Toggle this switch at any time without reloading the driver.*

### 2.3. Deliberate Hardware Reset
- Click **Trigger Reset** on the main window or right-click the **System Tray icon** -> select **Trigger Reset**.
- This generates a controlled 100ms hardware pulse on the configured reset line.

### 2.4. Driver Restoration
- To completely revert to the original factory Linux driver, click **Restore Original Driver**.

---

## 3. Settings & Preferences

Click **⚙ Settings** (top-right gear icon) to customize:
- **Hardware Pin Mapping**:
  - Choose which pin drives **Reset** vs **Boot Mode** (DTR = Reset / RTS = Boot, or vice-versa).
- **System Startup**:
  - Check **Start Minimized on Boot** to run the tool silently in the background on Linux login.

---

## 4. System Tray Integration

The application lives in your system tray:
- **🟢 Green**: Patch is active and protecting connected devices.
- **🟠 Amber**: Driver is patched but protection is temporarily inactive.
- **⚪ Gray**: Default factory kernel driver is loaded.
- **Tray Menu Actions**:
  - **Open Control Panel**: Bring the main interface to focus.
  - **Trigger Reset**: Fire a manual reset pulse on the active port.
  - **Quit**: Exit the application.

---

## 5. Supported Hardware & Drivers
- `ftdi_sio` (FTDI FT232R, FT2232, etc.)
- `cp210x` (Silicon Labs CP2102, CP2104)
- `ch341` (WCH CH340, CH341)
- `pl2303` (Prolific PL2303)
- `cdc_acm` (Standard USB CDC-ACM devices)
