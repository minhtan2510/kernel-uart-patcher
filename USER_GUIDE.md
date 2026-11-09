# Kernel UART Patcher — Quick Guide

A tool to block unwanted hardware resets when opening serial ports on Linux.

---

## 1. Launch

Double-click `Kernel_UART_Patcher` or run in terminal:
```bash
./Kernel_UART_Patcher
```
*(Requires Secure Boot disabled in BIOS).*

---

## 2. Basic Usage

### Step 1: Block Resets (Patch)
1. Select your port in **Connected Serial Port** (e.g. `/dev/ttyUSB0 (ftdi_sio)`).
2. Click **Patch <driver>** and enter your `sudo` password.
3. Status becomes **`PATCH ACTIVE` 🟢** — resets are now blocked for all apps.

### Step 2: Pause / Resume Protection
- Use the toggle switch:
  - **`PATCH ACTIVE` 🟢**: Reset suppression is ON.
  - **`PATCH INACTIVE` 🟠**: Default Linux behavior (turn this on when flashing firmware).

### Step 3: Trigger Hardware Reset (Deliberate)
- Click **Trigger Reset** (or right-click the System Tray icon → **Trigger Reset**) to send a manual reset pulse to the device.

### Step 4: Restore Original Driver
- Click **Restore Original Driver** to revert to the factory Linux kernel driver at any time.

---

## 3. Settings (⚙)

Click the gear icon in the top-right corner to:
- **Pin Mapping**: Set which line triggers **Reset** vs **Boot** (DTR or RTS).
- **Startup**: Check **Start Minimized on Boot** to run silently in the system tray on login.

---

## 4. System Tray

Right-click the tray icon for quick controls:
- **🟢 Green**: Protected (Active)
- **🟠 Amber**: Protection Paused
- **⚪ Gray**: Stock Driver
- **Actions**: Open Control Panel, Trigger Reset, Quit.
