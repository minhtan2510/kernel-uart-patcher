#!/usr/bin/env python3
"""
Kernel UART Patcher — Ultra-Compact Modern Minimalist Control Panel (PyQt6 Edition).

A sleek, hardware-accelerated desktop utility to prevent Linux kernel
and userspace applications from asserting DTR/RTS on serial connection,
protecting connected MCUs, gimbals, and development boards from unwanted resets.
"""

import os
import sys
import subprocess
import re
import html
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QPlainTextEdit, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QMenu
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, pyqtProperty, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QKeySequence, QShortcut, QPainterPath
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "core", "uart_kernel_patch.sh"))

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
# Main Application Window
# ------------------------------------------------------------------------------
class UARTShieldApp(QWidget):
    """
    @brief Ultra-compact modern minimalist control widget for serial DTR/RTS reset shield.
    """
    WINDOW_WIDTH = 520
    WINDOW_HEIGHT = 520

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        super().__init__()
        self.devices = []
        self.is_operating = False
        self.is_port_locked = False
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
        root_layout.addWidget(self.txt_log)

        # 6. Footer Row (Status / Spinner + Clear Button)
        ftr = QHBoxLayout()
        self.lbl_footer = QLabel("Ready • Space to toggle")
        self.lbl_footer.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ftr.addWidget(self.lbl_footer)
        ftr.addStretch()

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
            # Prioritize physical USB-UART bridges (ttyUSB) before ACM/modem gadgets (ttyACM)
            ports.sort(key=lambda p: (0 if "ttyUSB" in p else 1, p))

            for port in ports:
                port_name = os.path.basename(port)
                driver = "unknown"
                desc = ""
                mod_link = f"/sys/class/tty/{port_name}/device/driver/module"
                if os.path.islink(mod_link):
                    driver = os.path.basename(os.path.realpath(mod_link))

                try:
                    out = subprocess.check_output(
                        ["udevadm", "info", "-q", "property", "-n", port],
                        stderr=subprocess.DEVNULL,
                        text=True
                    )
                    for line in out.splitlines():
                        if line.startswith("ID_MODEL_FROM_DATABASE="):
                            desc = line.split("=", 1)[1].strip()
                            break
                        elif line.startswith("ID_MODEL=") and not desc:
                            desc = line.split("=", 1)[1].strip().replace("_", " ")
                except Exception:
                    pass

                self.devices.append({"port": port, "driver": driver, "desc": desc})
        except Exception as e:
            self.log(f"Error scanning ports: {e}")

        # Populate combobox
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

    def _set_no_device_state(self):
        """
        @brief Update UI when no serial hardware is connected.
        """
        self.current_param_exists = False
        self.current_protected = False
        self.port_warning.hide()
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
