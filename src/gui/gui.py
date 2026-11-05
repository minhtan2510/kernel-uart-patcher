#!/usr/bin/env python3
"""
UART Shield — Ultra-Compact Modern Minimalist Control Panel (PyQt6 Edition).

A sleek, hardware-accelerated desktop utility to prevent Linux kernel
and userspace applications from asserting DTR/RTS on serial connection,
protecting connected MCUs, gimbals, and development boards from unwanted resets.
"""

import os
import sys
import subprocess
import re
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QPlainTextEdit, QMessageBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, pyqtProperty
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QKeySequence, QShortcut
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "core", "uart_kernel_patch.sh"))

# ------------------------------------------------------------------------------
# Modern Minimalist Palette (Tailwind Slate / Zinc inspired)
# ------------------------------------------------------------------------------
COLOR_BG = "#0b0f19"              # Deep midnight slate
COLOR_SURFACE = "#131b2e"         # Card surface
COLOR_SURFACE_HOVER = "#1c2742"   # Surface hover
COLOR_BORDER = "#1e293b"          # Base border
COLOR_CARD_BORDER = "#25334d"     # Distinct card border

COLOR_TEXT_PRIMARY = "#f8fafc"    # Crisp white
COLOR_TEXT_MUTED = "#94a3b8"      # Slate 400
COLOR_TEXT_DIM = "#64748b"        # Slate 500

COLOR_EMERALD = "#10b981"         # Emerald 500
COLOR_EMERALD_BG = "#064e3b"      # Deep emerald
COLOR_EMERALD_BORDER = "#059669"  # Emerald border

COLOR_AMBER = "#f59e0b"           # Amber 500
COLOR_AMBER_BG = "#451a03"        # Deep amber
COLOR_AMBER_BORDER = "#b45309"    # Amber border

COLOR_RED = "#ef4444"             # Red 500
COLOR_RED_BG = "#381313"          # Deep red
COLOR_RED_BORDER = "#7f1d1d"      # Red border
COLOR_RED_TEXT = "#fca5a5"        # Soft red text

COLOR_BLUE_BTN = "#2563eb"        # Blue 600
COLOR_BLUE_HOVER = "#3b82f6"      # Blue 500


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
        self.setFixedSize(46, 24)
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
            bg = QColor("#162033")
            border = QColor("#1e293b")
            thumb = QColor("#475569")
        elif self._checked:
            bg = QColor(COLOR_EMERALD)
            border = QColor(COLOR_EMERALD_BORDER)
            thumb = QColor("#ffffff")
        else:
            bg = QColor("#1e293b")
            border = QColor("#334155")
            thumb = QColor("#94a3b8")

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

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(thumb))
        p.drawEllipse(int(cx - tr), int(cy - tr), int(tr * 2), int(tr * 2))


# ------------------------------------------------------------------------------
# Clickable ComboBox with Double-Click Copy
# ------------------------------------------------------------------------------
class PortComboBox(QComboBox):
    """
    @brief Custom ComboBox that copies active port path on double-click.
    """
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


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
            for line in proc.stdout:
                clean = ansi_escape.sub('', line.rstrip())
                self.log_signal.emit(clean)

            proc.wait()
            rc = proc.returncode

            if rc == 0:
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
# Main Application Window
# ------------------------------------------------------------------------------
class UARTShieldApp(QWidget):
    """
    @brief Ultra-compact modern minimalist control widget for serial DTR/RTS reset shield.
    """
    WINDOW_WIDTH = 360
    HEIGHT_COLLAPSED = 315
    HEIGHT_EXPANDED = 465

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        super().__init__()
        self.devices = []
        self.is_operating = False
        self.is_port_locked = False
        self.log_expanded = False
        self.current_protected = False
        self.current_param_exists = False
        self.active_task_label = ""
        self.spinner_idx = 0
        self.worker = None

        self._setup_window()
        self._build_ui()
        self._setup_shortcuts()

        # Timers
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._step_spinner)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_devices)
        self.refresh_timer.start(3000)

        self.refresh_devices()

    def _setup_window(self):
        """
        @brief Configure window title, geometry, and hardware styling.
        """
        self.setWindowTitle("UART Shield")
        self.setFixedSize(self.WINDOW_WIDTH, self.HEIGHT_COLLAPSED)
        self._center_on_screen()

        # Comprehensive Modern Dark QSS Theme
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0f19;
                color: #f8fafc;
                font-family: 'SF Pro Display', 'Inter', 'Ubuntu', 'DejaVu Sans', sans-serif;
            }
            QFrame#card {
                background-color: #131b2e;
                border: 1px solid #25334d;
                border-radius: 12px;
            }
            QComboBox {
                background-color: #131b2e;
                border: 1px solid #25334d;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
                color: #f8fafc;
            }
            QComboBox:hover {
                border: 1px solid #3b82f6;
            }
            QComboBox QAbstractItemView {
                background-color: #131b2e;
                border: 1px solid #25334d;
                border-radius: 8px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                color: #f8fafc;
                padding: 4px;
                outline: none;
            }
            QPushButton#btn_scan {
                background-color: #192235;
                color: #f8fafc;
                border: 1px solid #25334d;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#btn_scan:hover {
                background-color: #24314c;
                border: 1px solid #3b82f6;
            }
            QPushButton#btn_patch {
                background-color: #192235;
                color: #f8fafc;
                border: 1px solid #25334d;
                border-radius: 7px;
                padding: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btn_patch:hover {
                background-color: #24314c;
                border: 1px solid #3b82f6;
            }
            QPushButton#btn_patch:disabled, QPushButton#btn_restore:disabled {
                background-color: #111726;
                color: #475569;
                border: 1px solid #1e293b;
            }
            QPushButton#btn_restore {
                background-color: #192235;
                color: #94a3b8;
                border: 1px solid #25334d;
                border-radius: 7px;
                padding: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btn_restore:hover {
                background-color: #381313;
                border: 1px solid #ef4444;
                color: #fca5a5;
            }
            QPushButton#btn_install {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                padding: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btn_install:hover {
                background-color: #3b82f6;
            }
            QPushButton#btn_install:disabled {
                background-color: #1a2336;
                color: #475569;
                border: 1px solid #25334d;
            }
            QPlainTextEdit {
                background-color: #060911;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px;
                font-family: 'SF Mono', 'JetBrains Mono', 'DejaVu Sans Mono', monospace;
                font-size: 11px;
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
            y = max(0, (geo.height() - self.HEIGHT_COLLAPSED) // 2)
            self.move(x, y)

    def _setup_shortcuts(self):
        """
        @brief Bind keyboard shortcuts for power-users.
        """
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._on_space_pressed)
        QShortcut(QKeySequence("Ctrl+R"), self, self.refresh_devices)
        QShortcut(QKeySequence(Qt.Key.Key_F5), self, self.refresh_devices)
        QShortcut(QKeySequence("Ctrl+L"), self, self._toggle_log_drawer)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

    def _build_ui(self):
        """
        @brief Construct layout with hardware-accelerated widgets.
        """
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 12)
        root_layout.setSpacing(8)

        # 1. Header Row (Title + Badge + Scan Button)
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        lbl_title = QLabel("UART Shield")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        hdr.addWidget(lbl_title)

        lbl_kernel = QLabel("KERNEL")
        lbl_kernel.setStyleSheet(
            "background: #162033; color: #94a3b8; font-size: 10px; font-weight: bold; "
            "border-radius: 4px; padding: 2px 6px; font-family: monospace;"
        )
        hdr.addWidget(lbl_kernel)
        hdr.addStretch()

        self.btn_scan = QPushButton("↻ Scan")
        self.btn_scan.setObjectName("btn_scan")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self.refresh_devices)
        hdr.addWidget(self.btn_scan)
        root_layout.addLayout(hdr)

        # 2. Port Selector Dropdown
        self.combo_ports = PortComboBox()
        self.combo_ports.currentIndexChanged.connect(self._on_device_selected)
        self.combo_ports.doubleClicked.connect(self._copy_port_to_clipboard)
        root_layout.addWidget(self.combo_ports)

        # 2b. Port In-Use Warning Chip (Hidden by default)
        self.port_warning = QFrame()
        self.port_warning.setStyleSheet(
            "background-color: #381f08; border: 1px solid #b45309; border-radius: 6px; padding: 3px 6px;"
        )
        pw_layout = QHBoxLayout(self.port_warning)
        pw_layout.setContentsMargins(4, 2, 4, 2)
        self.lbl_port_warning = QLabel("⚠ Port in use")
        self.lbl_port_warning.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        pw_layout.addWidget(self.lbl_port_warning)
        self.port_warning.hide()
        root_layout.addWidget(self.port_warning)

        # 3. Hero Status Card (Houses Status Pill + Switch + Desc + Optional Install CTA)
        self.card = QFrame()
        self.card.setObjectName("card")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(6)

        # Card Top Row: Status Pill (Left) + Animated Switch (Right)
        card_top = QHBoxLayout()
        self.lbl_pill = QLabel("Checking")
        self.lbl_pill.setStyleSheet(
            "background: #1a2336; color: #94a3b8; border: 1px solid #2e3d5b; "
            "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
        )
        card_top.addWidget(self.lbl_pill)
        card_top.addStretch()

        self.switch = AnimatedToggle()
        self.switch.toggled.connect(self._on_switch_toggled)
        card_top.addWidget(self.switch)
        card_layout.addLayout(card_top)

        # Subtitle description
        self.lbl_desc = QLabel("Checking serial DTR/RTS pin state...")
        self.lbl_desc.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent; border: none;")
        card_layout.addWidget(self.lbl_desc)

        # Prominent Install Button (Only visible if Stock Driver)
        self.btn_install = QPushButton("Install Kernel Shield")
        self.btn_install.setObjectName("btn_install")
        self.btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_install.clicked.connect(self.patch_driver)
        self.btn_install.hide()
        card_layout.addWidget(self.btn_install)

        root_layout.addWidget(self.card)

        # 4. Secondary Action Row (Rebuild Patch / Restore Stock)
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.btn_patch = QPushButton("Rebuild Patch")
        self.btn_patch.setObjectName("btn_patch")
        self.btn_patch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_patch.clicked.connect(self.patch_driver)
        actions.addWidget(self.btn_patch)

        self.btn_restore = QPushButton("Restore Stock")
        self.btn_restore.setObjectName("btn_restore")
        self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore.clicked.connect(self.restore_driver)
        actions.addWidget(self.btn_restore)
        root_layout.addLayout(actions)

        # 5. Activity Log Drawer (Collapsible)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.hide()
        root_layout.addWidget(self.txt_log)

        # 6. Footer Row (Status / Spinner + Log Toggle + Clear)
        ftr = QHBoxLayout()
        self.lbl_footer = QLabel("Ready • Space to toggle")
        self.lbl_footer.setStyleSheet("color: #64748b; font-size: 11px;")
        ftr.addWidget(self.lbl_footer)
        ftr.addStretch()

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet("background: transparent; color: #64748b; font-size: 11px; border: none;")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self.txt_log.clear)
        self.btn_clear.hide()
        ftr.addWidget(self.btn_clear)

        self.btn_log = QPushButton("Log ▸")
        self.btn_log.setStyleSheet("background: transparent; color: #94a3b8; font-size: 11px; font-weight: bold; border: none;")
        self.btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log.clicked.connect(self._toggle_log_drawer)
        ftr.addWidget(self.btn_log)

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
        self.lbl_footer.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
        QTimer.singleShot(delay_ms, lambda: (
            self.lbl_footer.setText("Ready • Space to toggle"),
            self.lbl_footer.setStyleSheet("color: #64748b; font-size: 11px;")
        ))

    def _on_space_pressed(self):
        """
        @brief Handle Space key press to toggle switch.
        """
        if not self.is_operating and self.switch._enabled:
            new_state = not self.switch.isChecked()
            self.switch.setChecked(new_state, animated=True)
            self._on_switch_toggled(new_state)

    def _toggle_log_drawer(self):
        """
        @brief Toggle collapsible activity log drawer and adjust window height.
        """
        self.log_expanded = not self.log_expanded
        if self.log_expanded:
            self.btn_log.setText("Log ▾")
            self.btn_clear.show()
            self.txt_log.show()
            self.setFixedHeight(self.HEIGHT_EXPANDED)
        else:
            self.btn_log.setText("Log ▸")
            self.btn_clear.hide()
            self.txt_log.hide()
            self.setFixedHeight(self.HEIGHT_COLLAPSED)

    def log(self, message: str):
        """
        @brief Append message to activity log.
        @param message Text string.
        """
        self.txt_log.appendPlainText(message)

    def set_operating(self, operating: bool, task_name: str = ""):
        """
        @brief Set UI controls busy/interactive state.
        @param operating True if busy running a background command.
        @param task_name Label for spinner.
        """
        self.is_operating = operating
        self.active_task_label = task_name

        self.btn_scan.setEnabled(not operating)
        self.btn_patch.setEnabled(not operating and not self.is_port_locked)
        self.btn_restore.setEnabled(not operating and not self.is_port_locked)
        self.btn_install.setEnabled(not operating and not self.is_port_locked)
        self.combo_ports.setEnabled(not operating)
        self.switch.setEnabled(not operating and self.current_param_exists)

        if operating:
            self.spinner_idx = 0
            self.spinner_timer.start(100)
        else:
            self.spinner_timer.stop()
            self.lbl_footer.setText(task_name if task_name else "Ready • Space to toggle")
            self.lbl_footer.setStyleSheet("color: #64748b; font-size: 11px;")

    def _step_spinner(self):
        """
        @brief Cycle ASCII spinner frame in footer.
        """
        if self.is_operating:
            frame = self.SPINNER_FRAMES[self.spinner_idx % len(self.SPINNER_FRAMES)]
            self.spinner_idx += 1
            self.lbl_footer.setText(f"{frame} {self.active_task_label}...")
            self.lbl_footer.setStyleSheet(f"color: {COLOR_BLUE_HOVER}; font-size: 11px; font-weight: bold;")

    # --------------------------------------------------------------------------
    # Device Scanning & State Resolution
    # --------------------------------------------------------------------------

    def refresh_devices(self):
        """
        @brief Scan available serial ports and query driver parameters.
        """
        if self.is_operating:
            return

        self.devices = []
        try:
            ports = [
                f"/dev/{f}"
                for f in os.listdir("/dev")
                if f.startswith("ttyUSB") or f.startswith("ttyACM")
            ]
            ports.sort()

            for port in ports:
                port_name = os.path.basename(port)
                driver = "unknown"
                mod_link = f"/sys/class/tty/{port_name}/device/driver/module"
                if os.path.islink(mod_link):
                    driver = os.path.basename(os.path.realpath(mod_link))

                self.devices.append({"port": port, "driver": driver})
        except Exception as e:
            self.log(f"Error scanning ports: {e}")

        # Populate combobox
        current_selection = self.combo_ports.currentText()
        self.combo_ports.blockSignals(True)
        self.combo_ports.clear()

        values = [f"{d['port']} ({d['driver']})" for d in self.devices]
        self.combo_ports.addItems(values)

        if values:
            if current_selection in values:
                self.combo_ports.setCurrentText(current_selection)
            else:
                self.combo_ports.setCurrentIndex(0)
            self.combo_ports.blockSignals(False)
            self._update_selected_info()
        else:
            self.combo_ports.addItem("No serial ports detected")
            self.combo_ports.blockSignals(False)
            self._set_no_device_state()

    def _check_port_lock(self, port_path: str):
        """
        @brief Check if an active process holds an open file descriptor on the port.
        @param port_path e.g. /dev/ttyUSB0
        @return Tuple (pid, process_name) or (None, None).
        """
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
            self.btn_install.setEnabled(False)
            self.btn_install.setToolTip(lock_msg)
            self.btn_patch.setEnabled(False)
            self.btn_patch.setToolTip(lock_msg)
            self.btn_restore.setEnabled(False)
            self.btn_restore.setToolTip(lock_msg)
        else:
            self.is_port_locked = False
            self.port_warning.hide()
            self.btn_install.setToolTip("")
            self.btn_patch.setToolTip("")
            self.btn_restore.setToolTip("")

        # Check kernel module parameter
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if os.path.isfile(param_file):
            self.current_param_exists = True
            try:
                with open(param_file, "r") as f:
                    val = f.read().strip()
                if val in ("Y", "1"):
                    # Shield Active
                    self.current_protected = True
                    self.lbl_pill.setText("● Shield Active")
                    self.lbl_pill.setStyleSheet(
                        f"background: {COLOR_EMERALD_BG}; color: {COLOR_EMERALD}; "
                        f"border: 1px solid {COLOR_EMERALD_BORDER}; border-radius: 10px; "
                        "padding: 3px 10px; font-size: 11px; font-weight: bold;"
                    )
                    self.lbl_desc.setText("Hardware resets blocked (DTR held HIGH)")
                    self.switch.setChecked(True)
                    self.switch.setEnabled(True)
                else:
                    # Shield Inactive
                    self.current_protected = False
                    self.lbl_pill.setText("○ Shield Inactive")
                    self.lbl_pill.setStyleSheet(
                        f"background: {COLOR_AMBER_BG}; color: {COLOR_AMBER}; "
                        f"border: 1px solid {COLOR_AMBER_BORDER}; border-radius: 10px; "
                        "padding: 3px 10px; font-size: 11px; font-weight: bold;"
                    )
                    self.lbl_desc.setText("Default Linux mode (DTR asserts on connect)")
                    self.switch.setChecked(False)
                    self.switch.setEnabled(True)

                self.btn_install.hide()
                self.btn_patch.setText("Rebuild Patch")
            except Exception:
                self._set_stock_state(driver)
        else:
            self._set_stock_state(driver)

        if not self.is_port_locked and not self.is_operating:
            self.btn_patch.setEnabled(True)
            self.btn_restore.setEnabled(True)

    def _set_stock_state(self, driver: str):
        """
        @brief Update UI when stock (unpatched) driver is in use.
        @param driver Driver module name.
        """
        self.current_param_exists = False
        self.current_protected = False
        self.lbl_pill.setText("△ Stock Driver")
        self.lbl_pill.setStyleSheet(
            "background: #1a2336; color: #94a3b8; border: 1px solid #2e3d5b; "
            "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
        )
        self.lbl_desc.setText(f"'{driver}' unpatched. Install shield to block resets.")
        self.switch.setChecked(False, animated=False)
        self.switch.setEnabled(False)

        self.btn_install.show()
        self.btn_install.setEnabled(not self.is_port_locked and not self.is_operating)
        self.btn_patch.setText("Patch Driver")

    def _set_no_device_state(self):
        """
        @brief Update UI when no serial hardware is connected.
        """
        self.current_param_exists = False
        self.current_protected = False
        self.port_warning.hide()
        self.lbl_pill.setText("No Device")
        self.lbl_pill.setStyleSheet(
            "background: #131926; color: #64748b; border: 1px solid #1e293b; "
            "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
        )
        self.lbl_desc.setText("Connect a USB-UART adapter or gimbal.")
        self.switch.setChecked(False, animated=False)
        self.switch.setEnabled(False)
        self.btn_install.hide()
        self.btn_patch.setEnabled(False)
        self.btn_restore.setEnabled(False)

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

        if not self.log_expanded:
            self._toggle_log_drawer()

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
        else:
            val = 1 if new_state else 0
            label = "Shield Active" if val == 1 else "Shield Inactive"
            self._run_core_command(["toggle", driver, str(val)], f"Set {label}")

    def patch_driver(self):
        """
        @brief Trigger driver patch installation.
        """
        driver = self._get_current_driver()
        confirm = QMessageBox.question(
            self,
            "Install Patch",
            f"Build and install DTR/RTS reset shield for '{driver}'?\n\n"
            "This will download, patch, and install the kernel driver module.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._run_core_command(["patch", driver, "-y"], f"Patching {driver}")

    def restore_driver(self):
        """
        @brief Trigger driver restore to stock Ubuntu version.
        """
        driver = self._get_current_driver()
        confirm = QMessageBox.question(
            self,
            "Restore Stock Driver",
            f"Restore original factory driver for '{driver}'?\n\n"
            "Warning: This will remove reset protection and restore standard Ubuntu DTR/RTS behavior.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._run_core_command(["restore", driver, "-y"], f"Restoring {driver}")


def main():
    if not os.path.isfile(CORE_SCRIPT):
        print(f"Error: Missing core script: {CORE_SCRIPT}")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = UARTShieldApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
