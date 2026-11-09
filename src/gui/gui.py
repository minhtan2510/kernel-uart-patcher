#!/usr/bin/env python3
"""
Kernel UART Patcher — Ultra-Compact Modern Minimalist Control Panel (PyQt6 Edition).

A sleek, hardware-accelerated desktop utility to prevent Linux kernel
and userspace applications from asserting DTR/RTS on serial connection,
protecting connected MCUs, gimbals, and development boards from unwanted resets.
"""

import os
import sys
import time
import fcntl
import termios
import struct
import subprocess
import re
import html
import ctypes
import gc
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QPlainTextEdit, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QMenu,
    QSystemTrayIcon, QCheckBox, QDialog, QFormLayout, QDialogButtonBox,
    QGroupBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, pyqtProperty, QSize, QPointF, QRectF
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QKeySequence, QShortcut,
    QPainterPath, QIcon, QPixmap
)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
    CORE_SCRIPT = os.path.join(BASE_DIR, "core", "uart_kernel_patch.sh")
    try:
        os.chmod(sys._MEIPASS, 0o755)
        core_dir = os.path.join(sys._MEIPASS, "core")
        if os.path.isdir(core_dir):
            os.chmod(core_dir, 0o755)
        if os.path.isfile(CORE_SCRIPT):
            os.chmod(CORE_SCRIPT, 0o755)
        patch_py = os.path.join(core_dir, "patch_driver.py")
        if os.path.isfile(patch_py):
            os.chmod(patch_py, 0o755)
    except Exception:
        pass
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    CORE_SCRIPT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "core", "uart_kernel_patch.sh"))


def _trim_memory():
    """
    @brief Reclaim unreferenced heap pages back to the OS via glibc malloc_trim.
    """
    try:
        gc.collect()
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass

AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "kernel-uart-patcher.desktop")
APP_ICON_DIR = os.path.expanduser("~/.local/share/icons")
APP_ICON_FILE = os.path.join(APP_ICON_DIR, "kernel-uart-patcher.png")

CONFIG_DIR = os.path.expanduser("~/.config/kernel-uart-patcher")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "dtr_role": "Reset",
    "rts_role": "Boot",
    "smart_bypass": True,
}


def load_user_config() -> dict:
    """
    @brief Load user settings from JSON file with fallback defaults.
    @return Configuration dictionary.
    """
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cfg.update(data)
        except Exception:
            pass
    return cfg


def save_user_config(cfg: dict):
    """
    @brief Persist configuration dictionary to user config directory.
    @param cfg Configuration dictionary to save.
    """
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# ------------------------------------------------------------------------------
# Modern Minimalist Light Palette (Tailwind Slate / Zinc inspired)
# ------------------------------------------------------------------------------
COLOR_BG = "#f8fafc"              # Slate 50 (Soft, clean background)
COLOR_SURFACE = "#ffffff"         # Pure white (Card surface & inputs)
COLOR_SURFACE_HOVER = "#f1f5f9"   # Slate 100 (Hover on white)
COLOR_BORDER = "#e2e8f0"          # Slate 200 (Clean divider/subtle border)
COLOR_CARD_BORDER = "#cbd5e1"     # Slate 300 (Crisp card & control border)

COLOR_TEXT_PRIMARY = "#0f172a"    # Slate 900 (High-contrast typography)
COLOR_TEXT_MUTED = "#475569"      # Slate 600 (Secondary readable labels)
COLOR_TEXT_DIM = "#94a3b8"        # Slate 400 (Placeholder / tertiary text)

COLOR_EMERALD = "#047857"         # Emerald 700 (High-contrast deep green)
COLOR_EMERALD_BG = "#dcfce7"      # Emerald 100 (Vibrant, clear status fill)
COLOR_EMERALD_BORDER = "#10b981"  # Emerald 500 (Vivid 2px outline)

COLOR_AMBER = "#92400e"           # Amber 800 (Rich, readable amber text)
COLOR_AMBER_BG = "#fef3c7"        # Amber 100 (Warm visible amber fill)
COLOR_AMBER_BORDER = "#f59e0b"    # Amber 500 (Vivid 2px outline)

COLOR_RED = "#dc2626"             # Red 600 (Danger action)
COLOR_RED_BG = "#fef2f2"          # Red 50 (Danger hover fill)
COLOR_RED_BORDER = "#fca5a5"      # Red 300 (Danger hover border)
COLOR_RED_TEXT = "#b91c1c"        # Red 700 (Danger text)

COLOR_BLUE_BTN = "#2563eb"        # Blue 600 (Primary action)
COLOR_BLUE_HOVER = "#1d4ed8"      # Blue 700

PILL_STYLE_BASE = (
    "border-radius: 9px; padding: 7px 18px; font-size: 14px; font-weight: bold; letter-spacing: 0.5px;"
)


# ------------------------------------------------------------------------------
# Custom Animated Toggle Switch (PyQt6 Hardware-Accelerated Canvas)
# ------------------------------------------------------------------------------
class AnimatedToggle(QWidget):
    """
    @brief Hardware-accelerated modern pill toggle switch with 60fps sliding animation.
    """
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = checked
        self._position = 1.0 if checked else 0.0
        self._enabled = True

        self.anim = QPropertyAnimation(self, b"thumbPosition", self)
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    @pyqtProperty(float)
    def thumbPosition(self) -> float:
        return self._position

    @thumbPosition.setter
    def thumbPosition(self, pos: float):
        self._position = pos
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animated: bool = True):
        """
        @brief Set the toggle state with optional smooth animation.
        @param checked Desired state.
        @param animated If True, animate transition.
        """
        if self._checked != checked:
            self._checked = checked
            if animated and self.isVisible():
                self.anim.stop()
                self.anim.setStartValue(self._position)
                self.anim.setEndValue(1.0 if checked else 0.0)
                self.anim.start()
            else:
                self._position = 1.0 if checked else 0.0
                self.update()

    def setEnabled(self, enabled: bool):
        """
        @brief Enable or lock the switch.
        @param enabled If False, gray out and ignore mouse clicks.
        """
        self._enabled = enabled
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            new_state = not self._checked
            self.setChecked(new_state, animated=True)
            self.toggled.emit(new_state)

    def paintEvent(self, event):
        """
        @brief Paint anti-aliased pill body and thumb circle with subpixel precision.
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        h = float(self.height())
        w = float(self.width())
        r = h / 2.0

        if not self._enabled:
            bg = QColor("#e2e8f0")
            border = QColor("#cbd5e1")
            thumb = QColor("#94a3b8")
        elif self._checked:
            bg = QColor("#10b981")
            border = QColor("#059669")
            thumb = QColor("#ffffff")
        else:
            bg = QColor("#e2e8f0")
            border = QColor("#cbd5e1")
            thumb = QColor("#ffffff")

        p.setPen(QPen(border, 1.2))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(1, 1, int(w - 2), int(h - 2), r, r)

        # Smooth thumb interpolation
        pad = 3.0
        tr = r - pad
        x_left = pad + tr
        x_right = w - pad - tr
        cx = x_left + (x_right - x_left) * self._position
        cy = r

        # Clean subtle outline/shadow for thumb in light mode
        p.setPen(QPen(QColor(0, 0, 0, 35), 1.0))
        p.setBrush(QBrush(thumb))
        p.drawEllipse(int(cx - tr), int(cy - tr), int(tr * 2), int(tr * 2))


# ------------------------------------------------------------------------------
# Clickable ComboBox with Double-Click Copy & Modern Vector Chevron
# ------------------------------------------------------------------------------
class PortItemDelegate(QStyledItemDelegate):
    """
    @brief Item delegate that renders smooth full-row background highlight
           without default Qt focus borders or frames.
    """
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), 32))

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        is_selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)

        rect = opt.rect
        row_rect = rect.adjusted(4, 2, -4, -2)

        # Draw smooth background fill on hover/select without any border
        if is_selected or is_hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e2e8f0"))
            painter.drawRoundedRect(row_rect, 6.0, 6.0)

        # Draw item text cleanly
        painter.setFont(opt.font)
        painter.setPen(QColor("#0f172a"))
        text_rect = rect.adjusted(12, 0, -12, 0)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), str(index.data() or ""))
        painter.restore()


class PortComboBox(QComboBox):
    """
    @brief Custom ComboBox that copies active port path on double-click,
           renders a crisp, modern anti-aliased vector chevron, and ensures
           clean full-row background hover without box outlines.
    """
    doubleClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(PortItemDelegate(self))
        self.view().setMouseTracking(True)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        """
        @brief Paint custom drop-down combobox with anti-aliased vector chevron.
        @param event Paint event.
        """
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#64748b"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        x = self.width() - 18
        y = self.height() / 2 - 2
        path = QPainterPath()
        path.moveTo(x - 4, y)
        path.lineTo(x, y + 4)
        path.lineTo(x + 4, y)
        p.drawPath(path)


# ------------------------------------------------------------------------------
# Background Command Worker (Non-blocking pkexec integration)
# ------------------------------------------------------------------------------
class CommandWorker(QThread):
    """
    @brief Asynchronous worker to execute core script via pkexec without freezing GUI.
    """
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, args: list, task_name: str):
        super().__init__()
        self.args = args
        self.task_name = task_name

    def run(self):
        cmd = ["pkexec", CORE_SCRIPT] + self.args
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            has_done = False
            for line in proc.stdout:
                clean = ansi_escape.sub('', line.rstrip())
                if clean.startswith("[DONE]"):
                    has_done = True
                self.log_signal.emit(clean)

            proc.wait()
            rc = proc.returncode

            if rc == 0:
                if not has_done:
                    self.log_signal.emit(f"[DONE] {self.task_name} succeeded.")
                self.finished_signal.emit(True, f"✓ {self.task_name} succeeded.")
            elif rc in (126, 127):
                self.log_signal.emit(f"[CANCEL] {self.task_name} cancelled by user.")
                self.finished_signal.emit(False, "Operation cancelled.")
            else:
                self.log_signal.emit(f"[FAIL] {self.task_name} failed (code: {rc}).")
                self.finished_signal.emit(False, f"Failed (exit code {rc}).")
        except Exception as e:
            self.log_signal.emit(f"[ERROR] {e}")
            self.finished_signal.emit(False, f"Error: {e}")


# ------------------------------------------------------------------------------
# Hardware Reset Worker (Autonomous DTR/RTS pulse delivery)
# ------------------------------------------------------------------------------
class ResetWorker(QThread):
    """
    @brief Asynchronous worker to pulse DTR/RTS lines for MCU hardware reset.
    """
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, port: str, driver: str, was_patch_active: bool,
                 dtr_role: str = "Reset", rts_role: str = "Boot"):
        """
        @brief Initialize reset worker.
        @param port Serial port device path (e.g. /dev/ttyUSB0).
        @param driver Driver module name (e.g. cp210x, ftdi_sio).
        @param was_patch_active Whether kernel driver reset shield was active.
        @param dtr_role Assigned function for DTR pin ('Reset' or 'Boot').
        @param rts_role Assigned function for RTS pin ('Boot' or 'Reset').
        """
        super().__init__()
        self.port = port
        self.driver = driver
        self.was_patch_active = was_patch_active
        self.dtr_role = dtr_role
        self.rts_role = rts_role

    def _write_param(self, path: str, val: str):
        """
        @brief Write boolean flag to driver sysfs parameter.
        @param path Absolute path to sysfs parameter file.
        @param val 'Y' or 'N' string.
        """
        try:
            with open(path, "w") as f:
                f.write(val)
        except PermissionError:
            subprocess.run(
                ["pkexec", "tee", path],
                input=val.encode(),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    def _pulse_lines(self, port_path: str):
        """
        @brief Pulse Reset modem control line according to Pin Mapping.
        @param port_path TTY device path (e.g. /dev/ttyUSB0).
        """
        fd = os.open(port_path, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        try:
            reset_bit = termios.TIOCM_DTR if self.dtr_role == "Reset" else termios.TIOCM_RTS
            boot_bit = termios.TIOCM_RTS if self.dtr_role == "Reset" else termios.TIOCM_DTR

            # Normal Reboot (Run Mode):
            # Ensure Boot line is INACTIVE (HIGH) while Reset is pulsed LOW
            fcntl.ioctl(fd, termios.TIOCMBIC, struct.pack("I", boot_bit))
            time.sleep(0.02)
            fcntl.ioctl(fd, termios.TIOCMBIS, struct.pack("I", reset_bit))
            time.sleep(0.15)
            fcntl.ioctl(fd, termios.TIOCMBIC, struct.pack("I", reset_bit))
            time.sleep(0.05)
        finally:
            os.close(fd)

    def run(self):
        """
        @brief Execute reset sequence: temporarily unshield, pulse lines, and restore shield.
        """
        param_file = f"/sys/module/{self.driver}/parameters/disable_dtr_rts" if self.driver else ""
        has_param = bool(param_file and os.path.isfile(param_file))
        success = False

        try:
            if self.was_patch_active and has_param:
                self.log_signal.emit(f"[RESET] Temporarily disarming reset shield on {self.driver}...")
                self._write_param(param_file, "N")

            self.log_signal.emit(f"[RESET] Pulsing hardware reset on {self.port} (DTR={self.dtr_role}, RTS={self.rts_role})...")
            self._pulse_lines(self.port)

            self.log_signal.emit(f"[SUCCESS] Hardware reset triggered successfully on {self.port}.")
            success = True
            msg = f"Hardware reset {self.port} OK"

        except Exception as e:
            self.log_signal.emit(f"[ERROR] Hardware reset failed: {e}")
            success = False
            msg = f"Hardware reset failed: {e}"

        finally:
            if self.was_patch_active and has_param:
                time.sleep(0.05)
                try:
                    self._write_param(param_file, "Y")
                    self.log_signal.emit(f"[RESET] Reset shield re-armed on {self.driver}.")
                except Exception as e:
                    self.log_signal.emit(f"[WARN] Failed to re-arm shield: {e}")

            self.finished_signal.emit(success, msg)


# ------------------------------------------------------------------------------
# Settings & Pin Mapping Dialog
# ------------------------------------------------------------------------------
class PreferencesDialog(QDialog):
    """
    @brief Modal preferences dialog for Hardware Pin Mapping and Smart Flashing Bypass.
    """
    def __init__(self, parent=None, config=None, current_driver="", current_port=""):
        super().__init__(parent)
        self.setWindowTitle("Settings — Pin Mapping & Smart Flashing")
        self.setFixedSize(460, 380)
        self.config = dict(config or DEFAULT_CONFIG)
        self.current_driver = current_driver
        self.current_port = current_port
        self.saved = False

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 1. Hardware Pin Mapping Group
        grp_pins = QGroupBox("Hardware Pin Role Mapping")
        grp_pins.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        pin_layout = QFormLayout(grp_pins)
        pin_layout.setContentsMargins(12, 10, 12, 10)
        pin_layout.setSpacing(10)

        lbl_desc = QLabel("Assign serial modem control lines to target MCU Reset (EN) and Boot (GPIO0) pins:")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #475569; font-size: 11px; font-weight: normal;")
        pin_layout.addRow(lbl_desc)

        self.cmb_dtr = QComboBox()
        self.cmb_dtr.addItems(["Reset (NRST / EN)", "Boot Mode (GPIO0 / BOOT0)"])

        self.cmb_rts = QComboBox()
        self.cmb_rts.addItems(["Boot Mode (GPIO0 / BOOT0)", "Reset (NRST / EN)"])

        # Set initial values
        if self.config.get("dtr_role") == "Boot":
            self.cmb_dtr.setCurrentIndex(1)
            self.cmb_rts.setCurrentIndex(1)
        else:
            self.cmb_dtr.setCurrentIndex(0)
            self.cmb_rts.setCurrentIndex(0)

        self.cmb_dtr.currentIndexChanged.connect(self._on_dtr_changed)
        self.cmb_rts.currentIndexChanged.connect(self._on_rts_changed)

        pin_layout.addRow("DTR Line:", self.cmb_dtr)
        pin_layout.addRow("RTS Line:", self.cmb_rts)

        layout.addWidget(grp_pins)

        # 2. Smart Flashing Bypass Group
        grp_bypass = QGroupBox("Smart Flashing Bypass (Cải tiến 2)")
        grp_bypass.setStyleSheet(grp_pins.styleSheet())
        bypass_layout = QVBoxLayout(grp_bypass)
        bypass_layout.setContentsMargins(12, 10, 12, 10)
        bypass_layout.setSpacing(6)

        self.chk_bypass = QCheckBox("Enable Smart Flashing Bypass (Sequence Pattern)")
        self.chk_bypass.setChecked(self.config.get("smart_bypass", True))
        self.chk_bypass.setStyleSheet("font-weight: bold; font-size: 12px; color: #0f172a;")
        bypass_layout.addWidget(self.chk_bypass)

        lbl_bypass_desc = QLabel(
            "• Single open() events (gTune, MissionPlanner, monitors) are 100% blocked from resetting the MCU.\n"
            "• Rapid toggle sequences (esptool, avrdude, stm32flash) are automatically permitted for flashing."
        )
        lbl_bypass_desc.setWordWrap(True)
        lbl_bypass_desc.setStyleSheet("color: #475569; font-size: 11px;")
        bypass_layout.addWidget(lbl_bypass_desc)

        layout.addWidget(grp_bypass)

        # 3. Actions Row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        act_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background: transparent; color: #64748b; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 12px;")
        btn_cancel.clicked.connect(self.reject)
        act_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save Settings")
        btn_save.setStyleSheet("background-color: #2563eb; color: #ffffff; font-weight: bold; font-size: 12px; border: none; border-radius: 6px; padding: 5px 14px;")
        btn_save.clicked.connect(self._save_and_accept)
        act_row.addWidget(btn_save)

        layout.addLayout(act_row)

    def _on_dtr_changed(self, idx: int):
        """
        @brief Automatically invert RTS when DTR is modified.
        @param idx Selected index in DTR combo.
        """
        self.cmb_rts.blockSignals(True)
        self.cmb_rts.setCurrentIndex(0 if idx == 0 else 1)
        self.cmb_rts.blockSignals(False)

    def _on_rts_changed(self, idx: int):
        """
        @brief Automatically invert DTR when RTS is modified.
        @param idx Selected index in RTS combo.
        """
        self.cmb_dtr.blockSignals(True)
        self.cmb_dtr.setCurrentIndex(0 if idx == 0 else 1)
        self.cmb_dtr.blockSignals(False)

    def _save_and_accept(self):
        """
        @brief Apply changes to config dictionary and close dialog.
        """
        self.config["dtr_role"] = "Reset" if self.cmb_dtr.currentIndex() == 0 else "Boot"
        self.config["rts_role"] = "Boot" if self.cmb_rts.currentIndex() == 0 else "Reset"
        self.config["smart_bypass"] = self.chk_bypass.isChecked()
        save_user_config(self.config)
        self.saved = True
        self.accept()


# ------------------------------------------------------------------------------
# Main Application Window
# ------------------------------------------------------------------------------
class UARTShieldApp(QWidget):
    """
    @brief Ultra-compact modern minimalist control widget for serial DTR/RTS reset shield.
    """
    WINDOW_WIDTH = 520
    WINDOW_HEIGHT = 420

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, start_minimized: bool = False):
        super().__init__()
        self.start_minimized = start_minimized
        self.devices = []
        self._last_raw_ports = None
        self.is_operating = False
        self.is_port_locked = False
        self.current_protected = False
        self.current_param_exists = False
        self.active_task_label = ""
        self.spinner_idx = 0
        self.worker = None
        self._force_quit = False
        self._tray_last_state = ""
        self.tray = None
        self._tray_icons = {}
        self.config = load_user_config()
        self._last_flash_detect_count = {}

        self._setup_window()
        self._build_ui()
        self._setup_shortcuts()

        # Timers
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._step_spinner)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(3000)

        # Initial device scan first, then initialize tray with accurate state
        self.refresh_devices()
        self._apply_smart_bypass_to_driver()
        self._setup_tray()

        if self.start_minimized:
            self.hide()
            self.refresh_timer.setInterval(5000)
            _trim_memory()

    def _setup_window(self):
        """
        @brief Configure window title, geometry, and hardware styling.
        """
        self.setWindowTitle("Kernel UART Patcher")
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self._center_on_screen()

        # Comprehensive Modern Light QSS Theme
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                color: #0f172a;
                font-family: 'SF Pro Display', 'Inter', 'Ubuntu', 'DejaVu Sans', sans-serif;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 12px;
                padding-right: 28px;
                font-size: 13px;
                color: #0f172a;
            }
            QComboBox:hover {
                border: 1px solid #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 4px;
                outline: 0px;
                selection-background-color: transparent;
            }
            QPushButton#btn_scan {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btn_scan:hover {
                background-color: #f1f5f9;
                border: 1px solid #3b82f6;
            }
            QPushButton#btn_reset {
                background-color: #ffffff;
                color: #64748b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton#btn_reset:hover {
                background-color: #f1f5f9;
                color: #0f172a;
                border: 1px solid #94a3b8;
            }
            QPushButton#btn_reset:disabled {
                color: #cbd5e1;
                border: 1px solid #f1f5f9;
                background-color: transparent;
            }
            QPushButton#btn_settings {
                background-color: #ffffff;
                color: #64748b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton#btn_settings:hover {
                background-color: #f1f5f9;
                color: #0f172a;
                border: 1px solid #94a3b8;
            }
            QPushButton#btn_settings:disabled {
                color: #cbd5e1;
                border: 1px solid #f1f5f9;
                background-color: transparent;
            }
            QPushButton#btn_patch {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btn_patch:hover {
                background-color: #1d4ed8;
            }
            QPushButton#btn_patch[secondary="true"] {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
            }
            QPushButton#btn_patch[secondary="true"]:hover {
                background-color: #f1f5f9;
                border: 1px solid #3b82f6;
            }
            QPushButton#btn_restore {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 7px;
                padding: 8px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btn_restore:hover {
                background-color: #fef2f2;
                border: 1px solid #ef4444;
                color: #dc2626;
            }
            QPushButton#btn_patch:disabled, QPushButton#btn_restore:disabled {
                background-color: #f1f5f9;
                color: #94a3b8;
                border: 1px solid #e2e8f0;
            }
            QPlainTextEdit {
                background-color: #ffffff;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px 10px;
                font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace;
                font-size: 11px;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 2px 2px 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def _center_on_screen(self):
        """
        @brief Center window on the active screen.
        """
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = max(0, (geo.width() - self.WINDOW_WIDTH) // 2)
            y = max(0, (geo.height() - self.WINDOW_HEIGHT) // 2)
            self.move(x, y)

    def _setup_shortcuts(self):
        """
        @brief Bind keyboard shortcuts for power-users.
        """
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._on_space_pressed)
        QShortcut(QKeySequence("Ctrl+R"), self, self.refresh_devices)
        QShortcut(QKeySequence(Qt.Key.Key_F5), self, self.refresh_devices)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, lambda: self.patch_driver(force=True))
        QShortcut(QKeySequence("Ctrl+T"), self, self.trigger_reset)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_preferences)
        QShortcut(QKeySequence("Ctrl+Q"), self, self._quit_app)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

    def _build_ui(self):
        """
        @brief Construct layout with hardware-accelerated widgets.
        """
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 12)
        root_layout.setSpacing(8)

        # 1. Port Selector Dropdown & Scan Button (Single Row)
        port_row = QHBoxLayout()
        port_row.setSpacing(8)

        self.combo_ports = PortComboBox()
        self.combo_ports.currentIndexChanged.connect(self._on_device_selected)
        self.combo_ports.doubleClicked.connect(self._copy_port_to_clipboard)
        port_row.addWidget(self.combo_ports, stretch=1)

        self.btn_scan = QPushButton("↻ Scan")
        self.btn_scan.setObjectName("btn_scan")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self.refresh_devices)
        port_row.addWidget(self.btn_scan)

        root_layout.addLayout(port_row)

        # 2b. Port In-Use Warning Chip (Hidden by default)
        self.port_warning = QFrame()
        self.port_warning.setStyleSheet(
            "background-color: #fffbeb; border: 1px solid #f59e0b; border-radius: 6px; padding: 3px 6px;"
        )
        pw_layout = QHBoxLayout(self.port_warning)
        pw_layout.setContentsMargins(4, 2, 4, 2)
        self.lbl_port_warning = QLabel("⚠ Port in use")
        self.lbl_port_warning.setStyleSheet("color: #b45309; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        pw_layout.addWidget(self.lbl_port_warning)
        self.port_warning.hide()
        root_layout.addWidget(self.port_warning)

        # 3. Hero Status Card (Houses Status Pill + Switch + Desc)
        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.card.customContextMenuRequested.connect(self._show_card_context_menu)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 13, 14, 13)
        card_layout.setSpacing(8)

        # Card Top Row: Status Pill (Left) + Animated Switch (Right)
        card_top = QHBoxLayout()
        self.lbl_pill = QLabel("CHECKING")
        self.lbl_pill.setStyleSheet(
            f"background: #f1f5f9; color: #64748b; border: 2px solid #cbd5e1; {PILL_STYLE_BASE}"
        )
        card_top.addWidget(self.lbl_pill, alignment=Qt.AlignmentFlag.AlignVCenter)
        card_top.addStretch()

        self.switch = AnimatedToggle()
        self.switch.toggled.connect(self._on_switch_toggled)
        card_top.addWidget(self.switch, alignment=Qt.AlignmentFlag.AlignVCenter)
        card_layout.addLayout(card_top)

        # Subtitle description
        self.lbl_desc = QLabel("Checking serial DTR/RTS pin state...")
        self.lbl_desc.setStyleSheet("color: #475569; font-size: 12px; background: transparent; border: none;")
        card_layout.addWidget(self.lbl_desc)

        root_layout.addWidget(self.card)

        # 4. Action Row (Patch Driver / Restore Stock - 70/30 ratio)
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.btn_patch = QPushButton("Patch Driver")
        self.btn_patch.setObjectName("btn_patch")
        self.btn_patch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_patch.clicked.connect(self.patch_driver)
        actions.addWidget(self.btn_patch, stretch=7)

        self.btn_restore = QPushButton("Restore")
        self.btn_restore.setObjectName("btn_restore")
        self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore.clicked.connect(self.restore_driver)
        actions.addWidget(self.btn_restore, stretch=3)
        root_layout.addLayout(actions)

        # 5. Activity Log (Always Visible)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(1000)
        root_layout.addWidget(self.txt_log)

        # 6. Footer Row (Status / Spinner + Reset Device + Autostart + Clear Button)
        ftr = QHBoxLayout()
        self.lbl_footer = QLabel("Ready • Space to toggle")
        self.lbl_footer.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ftr.addWidget(self.lbl_footer)
        ftr.addStretch()

        self.btn_reset = QPushButton("Reset Device")
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.setToolTip("Pulse DTR/RTS lines to trigger hardware reset on target MCU (Ctrl+T)")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self.trigger_reset)
        ftr.addWidget(self.btn_reset)

        ftr.addSpacing(6)

        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.setToolTip("Hardware Pin Mapping (DTR/RTS) and Smart Flashing Bypass")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self.open_preferences)
        ftr.addWidget(self.btn_settings)

        ftr.addSpacing(10)

        self.chk_autostart = QCheckBox("Start on boot")
        self.chk_autostart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autostart.setStyleSheet("QCheckBox { color: #64748b; font-size: 11px; } QCheckBox:hover { color: #0f172a; }")
        self.chk_autostart.setChecked(self._is_autostart_enabled())
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        ftr.addWidget(self.chk_autostart)

        ftr.addSpacing(10)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet("background: transparent; color: #64748b; font-size: 11px; border: none; padding: 2px 4px;")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self.txt_log.clear)
        ftr.addWidget(self.btn_clear)

        root_layout.addLayout(ftr)

    def _copy_port_to_clipboard(self):
        """
        @brief Copy currently selected port name to system clipboard.
        """
        port = self._get_current_port()
        if port:
            clipboard = QApplication.clipboard()
            clipboard.setText(port)
            self._flash_footer(f"Copied {port} to clipboard!")

    def _flash_footer(self, message: str, delay_ms: int = 2500):
        """
        @brief Temporarily display toast message in the footer bar.
        @param message Text to display.
        @param delay_ms Duration in milliseconds.
        """
        self.lbl_footer.setText(message)
        self.lbl_footer.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        QTimer.singleShot(delay_ms, lambda: (
            self.lbl_footer.setText("Ready • Space to toggle"),
            self.lbl_footer.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ))

    def _on_space_pressed(self):
        """
        @brief Handle Space key press to toggle switch.
        """
        if not self.is_operating and self.switch._enabled:
            new_state = not self.switch.isChecked()
            self.switch.setChecked(new_state, animated=True)
            self._on_switch_toggled(new_state)

    def log(self, message: str):
        """
        @brief Append message to activity log with semantic color coding.
        @param message Raw text string.
        """
        lines = message.splitlines()
        if not lines:
            self.txt_log.appendHtml("<div style=\"height: 4px;\"></div>")
            return

        for line in lines:
            html_line = self._format_log_line(line)
            self.txt_log.appendHtml(html_line)

        # Auto-scroll to latest entry
        scrollbar = self.txt_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _format_log_line(self, line: str) -> str:
        """
        @brief Convert a plain text log line into styled HTML with semantic colors.
        @param line Raw text string.
        @return Styled HTML snippet.
        """
        line_clean = line.strip("\r\n")
        if not line_clean.strip():
            return "<div style=\"height: 4px;\"></div>"

        indent_match = re.match(r"^(\s+)", line_clean)
        indent_spaces = len(indent_match.group(1)) if indent_match else 0
        indent_prefix = "&nbsp;" * indent_spaces
        body = line_clean.lstrip()
        escaped_body = html.escape(body)

        # 1. Action header
        if re.match(r"^\[ACTION\]", body):
            return (
                f"<div style=\"margin-top: 4px; margin-bottom: 2px; "
                f"color: #1d4ed8; font-weight: bold;\">▶ {escaped_body}</div>"
            )

        # 2. Terminal Success
        if re.match(r"^\[(DONE|SUCCESS)\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #15803d; font-weight: bold;\">"
                f"✓ {escaped_body}</span>"
            )

        # 3. Terminal Failure
        if re.match(r"^(\[(FAIL|ERROR)\]|Error\b)", body):
            return (
                f"{indent_prefix}<span style=\"color: #dc2626; font-weight: bold;\">"
                f"✗ {escaped_body}</span>"
            )

        # 4. Cancel notice
        if re.match(r"^\[CANCEL\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #64748b; font-weight: bold;\">"
                f"⊘ {escaped_body}</span>"
            )

        # 5. Pipeline Step with [OK] or [DONE] suffix
        m_step_ok = re.match(r"^(\[\d+/\d+\].*?)(?:✓\s*)?\[(?:OK|DONE)\]$", body)
        if m_step_ok:
            step_desc = html.escape(m_step_ok.group(1).rstrip())
            return (
                f"{indent_prefix}<span style=\"color: #334155;\">{step_desc}</span> "
                f"<span style=\"color: #15803d; font-weight: bold;\">✓ [OK]</span>"
            )

        # 6. Pipeline Step with [ERR] or [FAIL] suffix
        m_step_err = re.match(r"^(\[\d+/\d+\].*?)(?:✗\s*)?\[(?:ERR|FAIL)\]$", body)
        if m_step_err:
            step_desc = html.escape(m_step_err.group(1).rstrip())
            return (
                f"{indent_prefix}<span style=\"color: #334155;\">{step_desc}</span> "
                f"<span style=\"color: #dc2626; font-weight: bold;\">✗ [ERR]</span>"
            )

        # 7. Step OK
        if re.match(r"^\[OK\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #16a34a; font-weight: bold;\">"
                f"✓ {escaped_body}</span>"
            )

        # 8. Step Error
        if re.match(r"^\[ERR\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #dc2626; font-weight: bold;\">"
                f"✗ {escaped_body}</span>"
            )

        # 9. Step Warning
        if re.match(r"^(\[WARN\]|\[\!\!\])", body):
            return (
                f"{indent_prefix}<span style=\"color: #b45309; font-weight: bold;\">"
                f"⚠ {escaped_body}</span>"
            )

        # 10. Step Info
        if re.match(r"^\[INFO\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #0284c7;\">"
                f"ℹ {escaped_body}</span>"
            )

        # 10b. Step Hardware Reset
        if re.match(r"^\[RESET\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #64748b; font-weight: bold;\">"
                f"↺ {escaped_body}</span>"
            )

        # 10c. Firmware Flashing Bypass
        if re.match(r"^\[FLASH\]", body):
            return (
                f"{indent_prefix}<span style=\"color: #0d9488; font-weight: bold;\">"
                f"⚡ {escaped_body}</span>"
            )

        # 11. Standard info / compiler chatter
        if indent_spaces > 0:
            return f"{indent_prefix}<span style=\"color: #64748b;\">{escaped_body}</span>"
        return f"<span style=\"color: #334155;\">{escaped_body}</span>"

    def set_operating(self, operating: bool, task_name: str = ""):
        """
        @brief Set UI controls busy/interactive state.
        @param operating True if busy running a background command.
        @param task_name Label for spinner.
        """
        self.is_operating = operating
        self.active_task_label = task_name

        self.btn_scan.setEnabled(not operating)
        self.btn_reset.setEnabled(not operating and bool(self.devices))
        self.btn_settings.setEnabled(not operating)
        self.btn_patch.setEnabled(
            not operating and not self.is_port_locked and not self.current_param_exists
        )
        self.btn_restore.setEnabled(
            not operating and not self.is_port_locked and self.current_param_exists
        )
        self.combo_ports.setEnabled(not operating)
        self.switch.setEnabled(not operating and self.current_param_exists)

        if operating:
            self.spinner_idx = 0
            self.spinner_timer.start(100)
        else:
            self.spinner_timer.stop()
            self.lbl_footer.setText(task_name if task_name else "Ready • Space to toggle")
            self.lbl_footer.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self._update_tray()

    def _step_spinner(self):
        """
        @brief Cycle ASCII spinner frame in footer.
        """
        if self.is_operating:
            frame = self.SPINNER_FRAMES[self.spinner_idx % len(self.SPINNER_FRAMES)]
            self.spinner_idx += 1
            self.lbl_footer.setText(f"{frame} {self.active_task_label}...")
            self.lbl_footer.setStyleSheet(f"color: {COLOR_BLUE_BTN}; font-size: 11px; font-weight: bold;")

    # --------------------------------------------------------------------------
    # Device Scanning & State Resolution
    # --------------------------------------------------------------------------

    @staticmethod
    def _get_port_metadata(port_name: str) -> tuple[str, str]:
        """
        @brief Extract driver module and device description with zero subprocess forks.
        @param port_name e.g. "ttyUSB0" or "ttyACM0"
        @return Tuple of (driver_name, description)
        """
        driver = "unknown"
        desc = ""

        # 1. Driver module via sysfs symlink
        mod_link = f"/sys/class/tty/{port_name}/device/driver/module"
        if os.path.islink(mod_link):
            try:
                driver = os.path.basename(os.path.realpath(mod_link))
            except Exception:
                pass

        # 2. Fast udev runtime database lookup (/run/udev/data/c<major>:<minor>)
        dev_stat_path = f"/sys/class/tty/{port_name}/dev"
        if os.path.isfile(dev_stat_path):
            try:
                with open(dev_stat_path, "r") as f:
                    maj_min = f.read().strip()
                udev_file = f"/run/udev/data/c{maj_min}"
                if os.path.isfile(udev_file):
                    with open(udev_file, "r", errors="ignore") as f:
                        for line in f:
                            if line.startswith("E:ID_MODEL_FROM_DATABASE="):
                                desc = line.split("=", 1)[1].strip()
                                break
                            elif line.startswith("E:ID_MODEL=") and not desc:
                                desc = line.split("=", 1)[1].strip().replace("_", " ")
            except Exception:
                pass

        # 3. Fallback to sysfs USB product descriptor
        if not desc:
            for candidate in (
                f"/sys/class/tty/{port_name}/device/../product",
                f"/sys/class/tty/{port_name}/device/../../product",
            ):
                if os.path.isfile(candidate):
                    try:
                        with open(candidate, "r") as f:
                            val = f.read().strip()
                        if val:
                            desc = val
                            break
                    except Exception:
                        pass

        # 4. Fallback to udevadm if udev database is not accessible
        if not desc:
            try:
                out = subprocess.check_output(
                    ["udevadm", "info", "-q", "property", "-n", f"/dev/{port_name}"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=1
                )
                for line in out.splitlines():
                    if line.startswith("ID_MODEL_FROM_DATABASE="):
                        desc = line.split("=", 1)[1].strip()
                        break
                    elif line.startswith("ID_MODEL=") and not desc:
                        desc = line.split("=", 1)[1].strip().replace("_", " ")
            except Exception:
                pass

        return driver, desc

    def refresh_devices(self):
        """
        @brief Scan available serial ports and query driver parameters with change detection.
        """
        if self.is_operating:
            return

        try:
            raw_ports = [
                f
                for f in os.listdir("/dev")
                if f.startswith("ttyUSB") or f.startswith("ttyACM")
            ]
        except Exception as e:
            self.log(f"Error scanning /dev: {e}")
            raw_ports = []

        # Prioritize physical USB-UART bridges (ttyUSB) before ACM/modem gadgets (ttyACM)
        raw_ports.sort(key=lambda p: (0 if "ttyUSB" in p else 1, p))

        # Check if physical port list actually changed
        ports_changed = (raw_ports != getattr(self, "_last_raw_ports", None))

        if ports_changed:
            self._last_raw_ports = raw_ports
            scanned = []
            for port_name in raw_ports:
                driver, desc = self._get_port_metadata(port_name)
                scanned.append({
                    "port": f"/dev/{port_name}",
                    "driver": driver,
                    "desc": desc
                })

            self.devices = scanned
            current_selection = self.combo_ports.currentText()
            self.combo_ports.blockSignals(True)
            self.combo_ports.clear()

            values = [
                f"{d['port']} ({d['driver']}) — {d['desc']}" if d.get("desc") else f"{d['port']} ({d['driver']})"
                for d in self.devices
            ]
            self.combo_ports.addItems(values)

            if values:
                if current_selection in values:
                    self.combo_ports.setCurrentText(current_selection)
                else:
                    self.combo_ports.setCurrentIndex(0)
            else:
                self.combo_ports.addItem("No serial ports detected")
            self.combo_ports.blockSignals(False)

        # Update driver parameters and tray status without clearing widget state
        if self.devices:
            self._update_selected_info()
        else:
            self._set_no_device_state()

    def _check_port_lock(self, port_path: str):
        """
        @brief Check if an active process holds an open file descriptor on the port.
        @param port_path e.g. /dev/ttyUSB0
        @return Tuple (pid, process_name) or (None, None).
        """
        # Skip process inspection when window is hidden in background
        if not self.isVisible():
            return None, None

        try:
            res = subprocess.run(
                ["fuser", port_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            pids = res.stdout.strip().split()
            if pids:
                pid = pids[0]
                comm = pid
                comm_file = f"/proc/{pid}/comm"
                if os.path.isfile(comm_file):
                    with open(comm_file, "r") as f:
                        comm = f.read().strip()
                return pid, comm
        except Exception:
            pass
        return None, None

    def _on_device_selected(self):
        self._update_selected_info()

    def _update_selected_info(self):
        """
        @brief Refresh status badge, toggle switch, and port lock warning.
        """
        idx = self.combo_ports.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            return

        self.btn_reset.setEnabled(not self.is_operating)

        dev = self.devices[idx]
        driver = dev["driver"]
        port = dev["port"]

        # Check process lock
        lock_pid, lock_name = self._check_port_lock(port)
        if lock_pid:
            self.is_port_locked = True
            lock_msg = f"Port is in use by {lock_name} (PID {lock_pid}). Close the application first."
            self.lbl_port_warning.setText(f"⚠ Port in use: {lock_name} (PID {lock_pid})")
            self.port_warning.show()
            self.btn_patch.setEnabled(False)
            self.btn_patch.setToolTip(lock_msg)
            self.btn_restore.setEnabled(False)
            self.btn_restore.setToolTip(lock_msg)
        else:
            self.is_port_locked = False
            self.port_warning.hide()
            self.btn_patch.setToolTip("")
            self.btn_restore.setToolTip("")

        # Check kernel module parameter
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if os.path.isfile(param_file):
            self.current_param_exists = True
            try:
                # Check flash detect count for debugging
                fcfile = f"/sys/module/{driver}/parameters/flash_detect_count"
                if os.path.isfile(fcfile):
                    try:
                        with open(fcfile, "r") as f:
                            cnt = int(f.read().strip())
                        last_cnt = self._last_flash_detect_count.get(driver, 0)
                        if cnt > last_cnt:
                            self._last_flash_detect_count[driver] = cnt
                            self.log(
                                f"[FLASH] Firmware flashing detected on {driver} ({port})! "
                                f"Bypassed DTR/RTS suppression (total: {cnt})."
                            )
                    except Exception:
                        pass

                with open(param_file, "r") as f:
                    val = f.read().strip()
                if val in ("Y", "1"):
                    # Patched Activated
                    self.current_protected = True
                    self.lbl_pill.setText("PATCH ACTIVE")
                    self.lbl_pill.setStyleSheet(
                        f"background: {COLOR_EMERALD_BG}; color: {COLOR_EMERALD}; "
                        f"border: 2px solid {COLOR_EMERALD_BORDER}; {PILL_STYLE_BASE}"
                    )
                    self.lbl_desc.setText("Hardware resets blocked (DTR held HIGH)")
                    self.switch.setChecked(True)
                    self.switch.setEnabled(True)
                else:
                    # Patched Inactive
                    self.current_protected = False
                    self.lbl_pill.setText("PATCH INACTIVE")
                    self.lbl_pill.setStyleSheet(
                        f"background: {COLOR_AMBER_BG}; color: {COLOR_AMBER}; "
                        f"border: 2px solid {COLOR_AMBER_BORDER}; {PILL_STYLE_BASE}"
                    )
                    self.lbl_desc.setText("Default Linux mode (DTR asserts on connect)")
                    self.switch.setChecked(False)
                    self.switch.setEnabled(True)

                self.btn_patch.hide()
                self.btn_restore.setText(f"Restore Original Driver ({driver})")
                self.btn_restore.setToolTip(f"Restore factory kernel driver for '{driver}' (removes reset shield)")
                self.btn_restore.show()
            except Exception:
                self._set_stock_state(driver)
        else:
            self._set_stock_state(driver)

        if not self.is_port_locked and not self.is_operating:
            if self.current_param_exists:
                self.btn_restore.setEnabled(True)
            else:
                self.btn_patch.setEnabled(True)

        self._update_tray()

    def _set_patch_btn_mode(self, is_secondary: bool):
        """
        @brief Toggle primary (blue) vs secondary (white) styling on Patch Driver button.
        @param is_secondary True for secondary outline button, False for primary blue CTA.
        """
        self.btn_patch.setProperty("secondary", is_secondary)
        self.btn_patch.style().unpolish(self.btn_patch)
        self.btn_patch.style().polish(self.btn_patch)

    def _set_stock_state(self, driver: str):
        """
        @brief Update UI when stock (unpatched) driver is in use.
        @param driver Driver module name.
        """
        self.current_param_exists = False
        self.current_protected = False
        self.lbl_pill.setText("SYSTEM DEFAULT")
        self.lbl_pill.setStyleSheet(
            f"background: #f1f5f9; color: #1e293b; border: 2px solid #94a3b8; {PILL_STYLE_BASE}"
        )
        self.lbl_desc.setText(f"'{driver}' unpatched. Patch driver to block serial resets.")
        self.switch.setChecked(False, animated=False)
        self.switch.setEnabled(False)

        self._set_patch_btn_mode(False)
        self.btn_patch.setText(f"Patch Driver ({driver})")
        self.btn_patch.setEnabled(not self.is_port_locked and not self.is_operating)
        self.btn_patch.show()

        self.btn_restore.setText("Restore")
        self.btn_restore.setEnabled(False)
        self.btn_restore.setToolTip("Cannot restore: driver is already the original factory driver.")
        self.btn_restore.show()

        self._update_tray()

    def _set_no_device_state(self):
        """
        @brief Update UI when no serial hardware is connected.
        """
        self.current_param_exists = False
        self.current_protected = False
        self.port_warning.hide()
        self.btn_reset.setEnabled(False)
        self.lbl_pill.setText("NO DEVICE")
        self.lbl_pill.setStyleSheet(
            f"background: #f8fafc; color: #64748b; border: 1.5px solid #cbd5e1; {PILL_STYLE_BASE}"
        )
        self.lbl_desc.setText("Connect a USB-UART adapter or gimbal.")
        self.switch.setChecked(False, animated=False)
        self.switch.setEnabled(False)

        self._set_patch_btn_mode(True)
        self.btn_patch.setText("Patch Driver")
        self.btn_patch.setEnabled(False)
        self.btn_patch.show()

        self.btn_restore.setText("Restore")
        self.btn_restore.setEnabled(False)
        self.btn_restore.setToolTip("")
        self.btn_restore.show()

        self._update_tray()

    def _get_current_driver(self) -> str:
        idx = self.combo_ports.currentIndex()
        if idx >= 0 and idx < len(self.devices):
            return self.devices[idx]["driver"]
        return "cp210x"

    def _get_current_port(self) -> str:
        idx = self.combo_ports.currentIndex()
        if idx >= 0 and idx < len(self.devices):
            return self.devices[idx]["port"]
        return ""

    # --------------------------------------------------------------------------
    # Asynchronous Execution via Core Script
    # --------------------------------------------------------------------------

    def _run_core_command(self, args: list, task_name: str):
        """
        @brief Launch background worker to execute script via pkexec.
        @param args CLI arguments.
        @param task_name Display label.
        """
        if self.is_operating:
            return

        self.set_operating(True, task_name)
        self.log(f"\n[ACTION] {task_name}")

        self.worker = CommandWorker(args, task_name)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self._on_command_finished)
        self.worker.start()

    def _on_command_finished(self, success: bool, msg: str):
        """
        @brief Handle background command completion.
        @param success True if return code was 0.
        @param msg Status description.
        """
        self.set_operating(False, msg)
        self.refresh_devices()
        if not success:
            self.log("[WARN] Operation cancelled or failed; switch reverted to match kernel state.")

    # --------------------------------------------------------------------------
    # System Tray & Background Companion
    # --------------------------------------------------------------------------

    def _make_tray_icon(self, state: str) -> QIcon:
        """
        @brief Render a sleek HiDPI USB-UART adapter icon with real-time status pip.
        @param state State string: 'active', 'inactive', 'default', or 'none'.
        @return QIcon instance with rendered hardware USB adapter and badge.
        """
        scale = 2.0
        logical_size = 22
        pixmap = QPixmap(int(logical_size * scale), int(logical_size * scale))
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. USB Type-A Metal Connector (Top)
        painter.setPen(QPen(QColor("#94a3b8"), 1.2))
        painter.setBrush(QBrush(QColor("#e2e8f0")))
        painter.drawRoundedRect(QRectF(6.0, 1.8, 10.0, 5.8), 1.2, 1.2)

        # Two precision contact pin cutouts in metal connector
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#64748b")))
        painter.drawRect(QRectF(7.6, 3.4, 2.0, 2.2))
        painter.drawRect(QRectF(12.4, 3.4, 2.0, 2.2))

        # 2. USB Dongle Body (Main Chassis)
        body_path = QPainterPath()
        body_path.addRoundedRect(QRectF(4.0, 7.2, 14.0, 12.8), 2.5, 2.5)

        if state == "none":
            # Disconnected: subtle outline with translucent fill
            painter.setPen(QPen(QColor("#94a3b8"), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(241, 245, 249, 120)))
            painter.drawPath(body_path)
        else:
            # Connected: Dark modern obsidian body with crisp metallic border
            painter.setPen(QPen(QColor("#475569"), 1.2))
            painter.setBrush(QBrush(QColor("#1e293b")))
            painter.drawPath(body_path)

            # Circuit / Grip ridges on chassis
            painter.setPen(QPen(QColor("#64748b"), 1.0))
            painter.drawLine(QPointF(6.5, 10.5), QPointF(10.0, 10.5))
            painter.drawLine(QPointF(6.5, 12.5), QPointF(10.0, 12.5))
            painter.drawLine(QPointF(6.5, 14.5), QPointF(9.0, 14.5))

            # 3. Status Badge Pip (Bottom-Right Corner)
            pip_center = QPointF(15.5, 15.5)
            pip_radius = 4.0

            # Protective dark cutout barrier separating badge from body
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#0f172a")))
            painter.drawEllipse(pip_center, pip_radius + 1.2, pip_radius + 1.2)

            if state == "active":
                pip_fill = QColor("#10b981")    # Emerald 500
                pip_border = QColor("#047857")  # Emerald 700
            elif state == "inactive":
                pip_fill = QColor("#f59e0b")    # Amber 500
                pip_border = QColor("#b45309")  # Amber 700
            else:
                pip_fill = QColor("#94a3b8")    # Slate 400
                pip_border = QColor("#475569")  # Slate 600

            painter.setPen(QPen(pip_border, 1.0))
            painter.setBrush(QBrush(pip_fill))
            painter.drawEllipse(pip_center, pip_radius, pip_radius)

            # High-contrast center glyph inside status pip
            if state == "active":
                # Checkmark (Shield Active)
                checkmark = QPainterPath()
                checkmark.moveTo(13.6, 15.4)
                checkmark.lineTo(14.9, 16.8)
                checkmark.lineTo(17.4, 14.2)
                painter.setPen(QPen(QColor("#ffffff"), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(checkmark)
            elif state == "inactive":
                # Minus / Bypass line (Pass-through mode)
                painter.setPen(QPen(QColor("#ffffff"), 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(13.6, 15.5), QPointF(17.4, 15.5))
            else:
                # Center indicator dot
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.drawEllipse(pip_center, 1.2, 1.2)

        painter.end()
        return QIcon(pixmap)

    def _setup_tray(self):
        """
        @brief Initialize system tray icon, context menu, and desktop integration.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        # Pre-cache static icons to avoid dynamic re-allocation during runtime
        self._tray_icons = {
            "active": self._make_tray_icon("active"),
            "inactive": self._make_tray_icon("inactive"),
            "default": self._make_tray_icon("default"),
            "none": self._make_tray_icon("none"),
        }

        self.tray = QSystemTrayIcon(self)

        # Context Menu
        self.tray_menu = QMenu()

        # 1. Informational header (current device & mode)
        self.tray_act_device = self.tray_menu.addAction("No device connected")
        self.tray_act_device.setEnabled(False)

        self.tray_menu.addSeparator()

        # 2. Checkable quick toggle
        self.tray_act_toggle = self.tray_menu.addAction("Block Reset Pins (Patch Active)")
        self.tray_act_toggle.setCheckable(True)
        self.tray_act_toggle.setEnabled(False)
        self.tray_act_toggle.triggered.connect(self._on_tray_toggle)

        self.tray_menu.addSeparator()

        # 3. Trigger Hardware Reset
        self.tray_act_reset = self.tray_menu.addAction("Trigger Hardware Reset")
        self.tray_act_reset.setEnabled(False)
        self.tray_act_reset.triggered.connect(self.trigger_reset)

        self.tray_menu.addSeparator()

        # 4. Settings & Autostart
        act_settings = self.tray_menu.addAction("Pin Mapping & Settings...")
        act_settings.triggered.connect(self.open_preferences)

        self.tray_act_autostart = self.tray_menu.addAction("Start Minimized on Boot")
        self.tray_act_autostart.setCheckable(True)
        self.tray_act_autostart.setChecked(self._is_autostart_enabled())
        self.tray_act_autostart.toggled.connect(self._on_autostart_toggled)

        self.tray_menu.addSeparator()

        # 4. Restore main window
        act_open = self.tray_menu.addAction("Open Control Panel")
        act_open.triggered.connect(self._show_window)

        # 5. Terminate app completely
        act_quit = self.tray_menu.addAction("Quit")
        act_quit.triggered.connect(self._quit_app)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)

        # Initialize directly with accurate post-scan state (prevents warning icon glitch)
        self._tray_last_state = ""
        self._update_tray()
        self.tray.show()

    def _update_tray(self):
        """
        @brief Synchronize tray icon, tooltip, and quick-toggle action with current kernel state.
        """
        if not hasattr(self, "tray") or self.tray is None:
            return

        driver = self._get_current_driver()
        port = self._get_current_port()

        if not self.devices:
            state = "none"
            label = "No Device Connected"
            tooltip = "Kernel UART Patcher — No device"
            toggle_checked = False
            toggle_enabled = False
        elif not self.current_param_exists:
            state = "default"
            label = f"{driver} ({port}) • SYSTEM DEFAULT"
            tooltip = f"Kernel UART Patcher\n{driver} ({port}) — SYSTEM DEFAULT (unpatched)"
            toggle_checked = False
            toggle_enabled = False
        elif self.current_protected:
            state = "active"
            label = f"{driver} ({port}) • PATCH ACTIVE"
            tooltip = f"Kernel UART Patcher\n{driver} ({port}) — PATCH ACTIVE ✓ (Resets blocked)"
            toggle_checked = True
            toggle_enabled = True
        else:
            state = "inactive"
            label = f"{driver} ({port}) • PATCH INACTIVE"
            tooltip = f"Kernel UART Patcher\n{driver} ({port}) — PATCH INACTIVE (DTR asserts on connect)"
            toggle_checked = False
            toggle_enabled = True

        if state != self._tray_last_state:
            cached_icon = self._tray_icons.get(state)
            if cached_icon is None:
                cached_icon = self._make_tray_icon(state)
                self._tray_icons[state] = cached_icon
            self.tray.setIcon(cached_icon)
            self._tray_last_state = state

        self.tray.setToolTip(tooltip)
        self.tray_act_device.setText(label)
        self.tray_act_toggle.setChecked(toggle_checked)
        self.tray_act_toggle.setEnabled(toggle_enabled and not self.is_operating)

        if port and self.devices:
            self.tray_act_reset.setText(f"Trigger Reset ({port})")
            self.tray_act_reset.setEnabled(not self.is_operating)
        else:
            self.tray_act_reset.setText("Trigger Hardware Reset")
            self.tray_act_reset.setEnabled(False)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """
        @brief Handle user click on tray icon.
        @param reason Click reason enum.
        """
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _on_tray_toggle(self, checked: bool):
        """
        @brief Handle quick-toggle action triggered from tray context menu.
        @param checked True if requested PATCH ACTIVE, False for PATCH INACTIVE.
        """
        if not self.current_param_exists or self.is_operating:
            self.tray_act_toggle.setChecked(self.current_protected)
            return

        self.switch.setChecked(checked, animated=False)
        self._on_switch_toggled(checked)

    def _is_autostart_enabled(self) -> bool:
        """
        @brief Check if autostart desktop entry currently exists.
        @return True if enabled, False otherwise.
        """
        return os.path.isfile(AUTOSTART_FILE)

    def _get_autostart_exec_command(self) -> str:
        """
        @brief Resolve the absolute command path to launch this tool minimized.
        @return Command string suitable for desktop entry Exec field.
        """
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --minimized'

        # When running from source, prefer root binary if available, else scripts/run.sh
        root_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
        binary_path = os.path.join(root_dir, "Kernel UART Patcher")
        if os.path.isfile(binary_path) and os.access(binary_path, os.X_OK):
            return f'"{binary_path}" --minimized'

        run_sh = os.path.join(root_dir, "scripts", "run.sh")
        if os.path.isfile(run_sh) and os.access(run_sh, os.X_OK):
            return f'"{run_sh}" --minimized'

        return f'"{sys.executable}" "{os.path.abspath(__file__)}" --minimized'

    def _ensure_app_icon_saved(self):
        """
        @brief Persist vector tray icon as PNG for desktop environment integration.
        """
        try:
            os.makedirs(APP_ICON_DIR, exist_ok=True)
            if not os.path.isfile(APP_ICON_FILE):
                icon = self._make_tray_icon("active")
                pixmap = icon.pixmap(QSize(64, 64))
                pixmap.save(APP_ICON_FILE, "PNG")
        except Exception:
            pass

    def _on_autostart_toggled(self, enabled: bool):
        """
        @brief Handle toggle event for autostart on system boot.
        @param enabled True to enable autostart, False to disable.
        """
        # Synchronize UI controls without recursion
        if hasattr(self, "chk_autostart") and self.chk_autostart.isChecked() != enabled:
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(enabled)
            self.chk_autostart.blockSignals(False)

        if hasattr(self, "tray_act_autostart") and self.tray_act_autostart.isChecked() != enabled:
            self.tray_act_autostart.blockSignals(True)
            self.tray_act_autostart.setChecked(enabled)
            self.tray_act_autostart.blockSignals(False)

        try:
            if enabled:
                os.makedirs(AUTOSTART_DIR, exist_ok=True)
                self._ensure_app_icon_saved()
                exec_cmd = self._get_autostart_exec_command()

                icon_val = APP_ICON_FILE if os.path.isfile(APP_ICON_FILE) else "utilities-terminal"
                content = (
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Version=1.0\n"
                    "Name=Kernel UART Patcher\n"
                    "GenericName=Serial DTR/RTS Reset Shield\n"
                    "Comment=Prevent unwanted serial DTR/RTS resets on USB-UART adapters\n"
                    f"Exec={exec_cmd}\n"
                    f"Icon={icon_val}\n"
                    "Terminal=false\n"
                    "Categories=Utility;Development;\n"
                    "StartupNotify=false\n"
                    "X-GNOME-Autostart-enabled=true\n"
                )
                with open(AUTOSTART_FILE, "w") as f:
                    f.write(content)
                os.chmod(AUTOSTART_FILE, 0o755)
                self.log("[SUCCESS] Autostart on boot enabled.")
                self._flash_footer("✓ Autostart on boot enabled")
            else:
                if os.path.isfile(AUTOSTART_FILE):
                    os.remove(AUTOSTART_FILE)
                self.log("[INFO] Autostart on boot disabled.")
                self._flash_footer("Autostart disabled")
        except Exception as e:
            self.log(f"[ERROR] Failed to update autostart setting: {e}")
            if hasattr(self, "chk_autostart"):
                self.chk_autostart.blockSignals(True)
                self.chk_autostart.setChecked(self._is_autostart_enabled())
                self.chk_autostart.blockSignals(False)
            if hasattr(self, "tray_act_autostart"):
                self.tray_act_autostart.blockSignals(True)
                self.tray_act_autostart.setChecked(self._is_autostart_enabled())
                self.tray_act_autostart.blockSignals(False)

    def _show_window(self):
        """
        @brief Restore, focus, and raise the main application window.
        """
        self.refresh_timer.setInterval(3000)
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self.refresh_devices()

    def _quit_app(self):
        """
        @brief Terminate application process completely, bypassing hide-to-tray.
        """
        self._force_quit = True
        QApplication.quit()

    def closeEvent(self, event):
        """
        @brief Intercept window close to hide to tray if available; quit if forced.
        @param event Close event to accept or ignore.
        """
        tray_available = hasattr(self, "tray") and self.tray is not None and self.tray.isVisible()
        if self._force_quit or not tray_available:
            event.accept()
            return

        event.ignore()
        self.hide()
        self.refresh_timer.setInterval(5000)
        _trim_memory()

    # --------------------------------------------------------------------------
    # Action Handlers
    # --------------------------------------------------------------------------

    def _on_switch_toggled(self, new_state: bool):
        """
        @brief Handle switch toggle event.
        @param new_state True for ON, False for OFF.
        """
        driver = self._get_current_driver()
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if not os.path.isfile(param_file):
            self.patch_driver()
            return

        label = "PATCH ACTIVE" if new_state else "PATCH INACTIVE"
        val_str = "Y" if new_state else "N"

        # 1. Attempt direct sysfs write (instant, 0-friction, no root password dialog)
        try:
            with open(param_file, "w") as f:
                f.write(val_str)
            self.log(f"[SUCCESS] {label} set via sysfs (instant).")
            self._update_selected_info()
            self._flash_footer(f"✓ {label}")
            return
        except PermissionError:
            self.log(f"[INFO] Direct sysfs write restricted, elevating via pkexec...")
        except Exception as e:
            self.log(f"[WARN] Direct sysfs write failed ({e}), attempting pkexec fallback...")

        # 2. Fallback to pkexec if permissions not yet 0666
        val_arg = "1" if new_state else "0"
        self._run_core_command(["toggle", driver, val_arg], f"Set {label}")

    def patch_driver(self, force: bool = False):
        """
        @brief Trigger driver patch installation or forced rebuild.
        @param force True if manually forced rebuild.
        """
        driver = self._get_current_driver()
        port = self._get_current_port()
        title = "Force Rebuild Patch" if force else "Install Patch"
        msg = (
            f"Rebuild and reinstall DTR/RTS reset shield for '{driver}' ({port})?\n\n"
            "This will recompile and reinstall the kernel driver module."
            if force
            else f"Build and install DTR/RTS reset shield for '{driver}' ({port})?\n\n"
            "This will download, patch, and install the kernel driver module."
        )
        confirm = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        task_label = f"Rebuilding {driver}" if force else f"Patching {driver}"
        self._run_core_command(["patch", driver, "-y"], task_label)

    def _show_card_context_menu(self, pos):
        """
        @brief Developer context menu on hero card for advanced actions.
        @param pos Position where context menu was requested.
        """
        driver = self._get_current_driver()
        if not driver or self.is_operating or not self.current_param_exists:
            return

        menu = QMenu(self)
        action_rebuild = menu.addAction(f"Force Rebuild Driver ({driver})")
        action_rebuild.setEnabled(not self.is_port_locked and not self.is_operating)
        chosen = menu.exec(self.card.mapToGlobal(pos))
        if chosen == action_rebuild:
            self.patch_driver(force=True)

    def _has_driver_backup(self, driver: str) -> bool:
        """
        @brief Check if a local backup file exists for the given driver.
        @param driver Driver module name (e.g. cp210x, cdc_acm).
        @return True if local backup file exists, False otherwise.
        """
        backup_dir = "/var/backups/uart_dtr_patch"
        if not os.path.isdir(backup_dir):
            return False
        if os.path.isfile(os.path.join(backup_dir, f"{driver}.path")):
            return True
        norm_driver = driver.replace("-", "_")
        try:
            for fname in os.listdir(backup_dir):
                if fname.replace("-", "_").startswith(norm_driver) and fname.endswith(".orig"):
                    return True
        except (PermissionError, FileNotFoundError):
            return False
        return False

    def restore_driver(self):
        """
        @brief Trigger driver restore to stock Ubuntu version.
        """
        driver = self._get_current_driver()
        port = self._get_current_port()

        if not self._has_driver_backup(driver):
            confirm = QMessageBox.question(
                self,
                "Backup Not Found - Recover from APT?",
                f"Backup file not found for driver '{driver}' ({port}).\n\n"
                "The local backup directory (/var/backups/uart_dtr_patch) does not exist or has been removed.\n\n"
                "Would you like to download and restore the official stock driver from Ubuntu APT repositories?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
        else:
            confirm = QMessageBox.question(
                self,
                "Restore Original Driver",
                f"Restore original system default driver for '{driver}' ({port})?\n\n"
                "Warning: This will remove reset protection and restore standard Ubuntu DTR/RTS behavior.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._run_core_command(["restore", driver, "-y"], f"Restoring {driver}")

    def trigger_reset(self):
        """
        @brief Trigger hardware reset sequence on currently selected serial port.
        """
        if self.is_operating:
            return

        port = self._get_current_port()
        driver = self._get_current_driver()
        if not port or not os.path.exists(port):
            self.log("[WARN] No valid serial port connected to reset.")
            return

        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts" if driver else ""
        was_patch_active = False
        if param_file and os.path.isfile(param_file):
            try:
                with open(param_file, "r") as f:
                    was_patch_active = f.read().strip() in ("Y", "1")
            except Exception:
                was_patch_active = self.current_protected

        dtr_role = self.config.get("dtr_role", "Reset")
        rts_role = self.config.get("rts_role", "Boot")

        self.set_operating(True, f"Resetting {port}")
        self.worker = ResetWorker(
            port, driver, was_patch_active,
            dtr_role=dtr_role, rts_role=rts_role
        )
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self._on_reset_finished)
        self.worker.start()

    def open_preferences(self):
        """
        @brief Open Preferences dialog for Pin Mapping and Smart Bypass configuration.
        """
        dialog = PreferencesDialog(
            parent=self,
            config=self.config,
            current_driver=self._get_current_driver(),
            current_port=self._get_current_port()
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved:
            self.config = dialog.config
            self._apply_smart_bypass_to_driver()
            self.log(
                f"[INFO] Settings updated: DTR={self.config.get('dtr_role')}, "
                f"RTS={self.config.get('rts_role')}, "
                f"SmartBypass={'ON' if self.config.get('smart_bypass') else 'OFF'}"
            )
            self._flash_footer("✓ Settings saved")

    def _apply_smart_bypass_to_driver(self):
        """
        @brief Synchronize smart_bypass setting to active kernel module parameter.
        """
        driver = self._get_current_driver()
        param_file = f"/sys/module/{driver}/parameters/smart_bypass"
        if os.path.isfile(param_file):
            val_str = "Y" if self.config.get("smart_bypass", True) else "N"
            try:
                with open(param_file, "w") as f:
                    f.write(val_str)
            except PermissionError:
                try:
                    subprocess.run(
                        ["pkexec", "tee", param_file],
                        input=val_str.encode(),
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass
            except Exception:
                pass

    def _on_reset_finished(self, success: bool, msg: str):
        """
        @brief Handle reset worker completion and refresh UI state.
        @param success True if reset pulse succeeded.
        @param msg Status message.
        """
        self.set_operating(False)
        self._update_selected_info()
        self._flash_footer(f"✓ {msg}" if success else f"✗ {msg}")

        # Show desktop notification if minimized to tray
        if not self.isVisible() and hasattr(self, "tray") and self.tray is not None:
            icon = QSystemTrayIcon.MessageIcon.Information if success else QSystemTrayIcon.MessageIcon.Warning
            port = self._get_current_port()
            self.tray.showMessage("Kernel UART Patcher", f"Hardware reset on {port}: {msg}", icon, 2500)


def main():
    if not os.path.isfile(CORE_SCRIPT):
        print(f"Error: Missing core script: {CORE_SCRIPT}")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    start_minimized = ("--minimized" in sys.argv or "-m" in sys.argv)
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()

    window = UARTShieldApp(start_minimized=start_minimized and tray_available)
    if not (start_minimized and tray_available):
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
