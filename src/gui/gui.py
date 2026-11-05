#!/usr/bin/env python3
"""
UART Shield — Ultra-Compact Modern Minimalist Control Panel.

A sleek, lightweight desktop utility to prevent Linux kernel
and userspace applications from asserting DTR/RTS on serial connection,
protecting connected MCUs, gimbals, and development boards from unwanted resets.
"""

import os
import sys
import subprocess
import threading
import queue
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "core", "uart_kernel_patch.sh"))

# ------------------------------------------------------------------------------
# Typography & Dynamic Font Resolution
# ------------------------------------------------------------------------------
def resolve_best_font(preferred_list: list, fallback: str = "sans-serif") -> str:
    """
    @brief Resolve the highest priority font available on the host system.
    @param preferred_list List of preferred font names.
    @param fallback Safe fallback name.
    @return Verified font family name.
    """
    try:
        available = set(tkfont.families())
        for name in preferred_list:
            if name in available:
                return name
    except Exception:
        pass
    return fallback


# Primary UI font (Open geometric sans with high x-height for readability)
FONT_UI = resolve_best_font(
    ["Google Sans", "SF Pro Display", "Ubuntu", "Inter", "DejaVu Sans"],
    "sans-serif"
)

# Monospace font for technical logs and hardware tags
FONT_MONO = resolve_best_font(
    ["SF Mono", "Fira Code", "JetBrains Mono", "DejaVu Sans Mono"],
    "monospace"
)

# ------------------------------------------------------------------------------
# Modern Minimalist Palette (Tailwind Slate / Zinc inspired)
# ------------------------------------------------------------------------------
COLOR_BG = "#090d16"           # Deep slate root background
COLOR_SURFACE = "#111726"      # Card / container surface
COLOR_SURFACE_HOVER = "#182238"# Surface on hover
COLOR_BORDER = "#1e293b"       # 1px crisp border
COLOR_BORDER_FOCUS = "#3b82f6" # Focus border

COLOR_TEXT_PRIMARY = "#f8fafc" # Crisp white
COLOR_TEXT_MUTED = "#94a3b8"   # Slate 400
COLOR_TEXT_DIM = "#64748b"     # Slate 500

COLOR_EMERALD = "#10b981"      # Emerald 500 (Protected active)
COLOR_EMERALD_BG = "#064e3b"   # Emerald deep badge bg
COLOR_EMERALD_BORDER = "#059669"

COLOR_AMBER = "#f59e0b"        # Amber 500 (Unprotected warning)
COLOR_AMBER_BG = "#451a03"
COLOR_AMBER_BORDER = "#b45309"

COLOR_RED = "#ef4444"          # Red 500
COLOR_RED_BG = "#381313"
COLOR_RED_BORDER = "#7f1d1d"
COLOR_RED_TEXT = "#fca5a5"

COLOR_BLUE_BTN = "#2563eb"     # Blue 600
COLOR_BLUE_BTN_HOVER = "#3b82f6"

COLOR_BTN_SECONDARY = "#192235"
COLOR_BTN_SECONDARY_HOVER = "#24314c"
COLOR_BTN_SECONDARY_BORDER = "#27354f"


# ------------------------------------------------------------------------------
# Custom UI Components (Modern Switch & Flat Button)
# ------------------------------------------------------------------------------
class ModernSwitch(tk.Canvas):
    """
    @brief Crisp interactive pill toggle switch for runtime parameter switching.
    """
    def __init__(
        self,
        parent,
        state: bool = True,
        command=None,
        width: int = 46,
        height: int = 24,
        bg_card: str = COLOR_SURFACE
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg_card,
            highlightthickness=0,
            cursor="hand2"
        )
        self.state = state
        self.enabled = True
        self.command = command
        self.width = width
        self.height = height

        self.bind("<Button-1>", self._on_click)
        self.draw()

    def draw(self):
        """
        @brief Render anti-aliased pill geometry and thumb.
        """
        self.delete("all")
        h = self.height
        w = self.width
        r = h // 2

        if not self.enabled:
            bg = "#162033"
            border = "#1e293b"
            thumb = "#475569"
            tx = r
        elif self.state:
            bg = COLOR_EMERALD
            border = COLOR_EMERALD_BORDER
            thumb = "#ffffff"
            tx = w - r
        else:
            bg = "#1e293b"
            border = "#334155"
            thumb = "#94a3b8"
            tx = r

        # Pill background (arcs + center rectangle)
        self.create_oval(1, 1, h - 1, h - 1, fill=bg, outline=border)
        self.create_oval(w - h + 1, 1, w - 1, h - 1, fill=bg, outline=border)
        self.create_rectangle(r, 1, w - r, h - 1, fill=bg, outline="")
        self.create_line(r, 1, w - r, 1, fill=border)
        self.create_line(r, h - 1, w - r, h - 1, fill=border)

        # Thumb circle
        pad = 3
        tr = r - pad
        self.create_oval(tx - tr, pad, tx + tr, h - pad, fill=thumb, outline="")

    def _on_click(self, _):
        """
        @brief Handle user click event on switch.
        """
        if self.enabled:
            self.state = not self.state
            self.draw()
            if self.command:
                self.command(self.state)

    def set_state(self, state: bool):
        """
        @brief Update switch toggle position without triggering command.
        @param state True for ON, False for OFF.
        """
        self.state = state
        self.draw()

    def set_enabled(self, enabled: bool):
        """
        @brief Enable or lock the switch.
        @param enabled True for active, False for locked/grayed out.
        """
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.draw()


class FlatButton(tk.Label):
    """
    @brief Minimalist flat button with hover feedback, border color, and optional danger theme.
    """
    def __init__(
        self,
        parent,
        text: str,
        command=None,
        bg=COLOR_BTN_SECONDARY,
        hover_bg=COLOR_BTN_SECONDARY_HOVER,
        fg=COLOR_TEXT_PRIMARY,
        hover_fg=None,
        font=(FONT_UI, 9, "bold"),
        padx=10,
        pady=6,
        state=tk.NORMAL,
        border_color=COLOR_BORDER,
        hover_border_color=None,
        **kwargs
    ):
        super().__init__(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            font=font,
            padx=padx,
            pady=pady,
            cursor="hand2",
            relief=tk.SOLID,
            borderwidth=1 if border_color else 0,
            highlightbackground=border_color if border_color else bg,
            **kwargs
        )
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.default_fg = fg
        self.hover_fg = hover_fg if hover_fg else fg
        self.border_color = border_color
        self.hover_border_color = hover_border_color if hover_border_color else border_color
        self.command = command
        self.state_val = state

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _):
        if self.state_val == tk.NORMAL:
            self.configure(
                bg=self.hover_bg,
                fg=self.hover_fg,
                highlightbackground=self.hover_border_color
            )

    def _on_leave(self, _):
        if self.state_val == tk.NORMAL:
            self.configure(
                bg=self.default_bg,
                fg=self.default_fg,
                highlightbackground=self.border_color
            )

    def _on_click(self, _):
        if self.state_val == tk.NORMAL and self.command:
            self.command()

    def set_state(self, state: str):
        """
        @brief Set button interactive state.
        @param state Either tk.NORMAL or tk.DISABLED.
        """
        self.state_val = state
        if state == tk.DISABLED:
            self.configure(cursor="arrow", fg=COLOR_TEXT_DIM, bg="#0d131f", highlightbackground="#162033")
        else:
            self.configure(cursor="hand2", fg=self.default_fg, bg=self.default_bg, highlightbackground=self.border_color)

    def set_theme(self, bg: str, hover_bg: str, fg=COLOR_TEXT_PRIMARY, border_color=None, hover_border_color=None, hover_fg=None):
        """
        @brief Reconfigure button theme dynamically.
        """
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.default_fg = fg
        self.hover_fg = hover_fg if hover_fg else fg
        if border_color is not None:
            self.border_color = border_color
            self.configure(highlightbackground=border_color)
        if hover_border_color is not None:
            self.hover_border_color = hover_border_color
        if self.state_val == tk.NORMAL:
            self.configure(bg=bg, fg=fg)


# ------------------------------------------------------------------------------
# Main Application Class
# ------------------------------------------------------------------------------
class UARTShieldApp:
    """
    @brief Ultra-compact modern minimalist control GUI for serial DTR/RTS reset shield.
    """
    WINDOW_WIDTH = 360
    HEIGHT_COLLAPSED = 320
    HEIGHT_EXPANDED = 470

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("UART Shield")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        # Center window on screen
        self._center_window(self.WINDOW_WIDTH, self.HEIGHT_COLLAPSED)

        # State tracking
        self.devices = []
        self.log_queue = queue.Queue()
        self.is_operating = False
        self.log_expanded = False
        self.current_protected = False
        self.spinner_idx = 0
        self.active_task_label = ""

        self._init_theme()
        self._build_ui()
        self._bind_shortcuts()
        self._start_log_consumer()

        # Initial device scan & auto refresh timer
        self.refresh_devices()
        self._schedule_auto_refresh()

    def _center_window(self, width: int, height: int):
        """
        @brief Center window on primary monitor.
        @param width Target window width in pixels.
        @param height Target window height in pixels.
        """
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _init_theme(self):
        """
        @brief Initialize ttk styling for clean dark mode combobox with modern fonts.
        """
        self.root.option_add('*TCombobox*Listbox.background', COLOR_SURFACE)
        self.root.option_add('*TCombobox*Listbox.foreground', COLOR_TEXT_PRIMARY)
        self.root.option_add('*TCombobox*Listbox.selectBackground', COLOR_BLUE_BTN)
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        self.root.option_add('*TCombobox*Listbox.font', (FONT_UI, 10))
        self.root.option_add('*TCombobox*Listbox.relief', tk.FLAT)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Compact.TCombobox",
            fieldbackground=COLOR_SURFACE,
            background=COLOR_BTN_SECONDARY,
            foreground=COLOR_TEXT_PRIMARY,
            darkcolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            arrowcolor=COLOR_TEXT_MUTED,
            bordercolor=COLOR_BORDER,
            padding=5
        )
        style.map(
            "Compact.TCombobox",
            fieldbackground=[("readonly", COLOR_SURFACE)],
            selectbackground=[("readonly", COLOR_SURFACE)],
            selectforeground=[("readonly", COLOR_TEXT_PRIMARY)]
        )

    def _bind_shortcuts(self):
        """
        @brief Register keyboard shortcuts for fast power-user access.
        """
        self.root.bind("<space>", lambda _: self._on_space_pressed())
        self.root.bind("<Control-r>", lambda _: self.refresh_devices())
        self.root.bind("<Control-R>", lambda _: self.refresh_devices())
        self.root.bind("<F5>", lambda _: self.refresh_devices())
        self.root.bind("<Control-l>", lambda _: self._toggle_log_drawer())
        self.root.bind("<Control-L>", lambda _: self._toggle_log_drawer())
        self.root.bind("<Escape>", lambda _: self.root.destroy())

    def _build_ui(self):
        """
        @brief Construct ultra-compact minimalist interface.
        """
        self.main_container = tk.Frame(self.root, bg=COLOR_BG, padx=14, pady=12)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # 1. Header Row (App Title + Kernel Pill + Refresh Button)
        header_row = tk.Frame(self.main_container, bg=COLOR_BG)
        header_row.pack(fill=tk.X, pady=(0, 8))

        lbl_title = tk.Label(
            header_row,
            text="UART SHIELD",
            font=(FONT_UI, 12, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_BG
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_badge = tk.Label(
            header_row,
            text="KERNEL",
            font=(FONT_MONO, 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg="#162033",
            padx=6,
            pady=2
        )
        lbl_badge.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_refresh = FlatButton(
            header_row,
            text="↻ Scan",
            command=self.refresh_devices,
            font=(FONT_UI, 9),
            padx=8,
            pady=3,
            border_color=COLOR_BORDER
        )
        self.btn_refresh.pack(side=tk.RIGHT)

        # 2. Port Selector Dropdown Row
        port_row = tk.Frame(self.main_container, bg=COLOR_BG)
        port_row.pack(fill=tk.X, pady=(0, 6))

        self.combo_ports = ttk.Combobox(
            port_row,
            state="readonly",
            font=(FONT_UI, 10),
            style="Compact.TCombobox"
        )
        self.combo_ports.pack(fill=tk.X, ipady=4)
        self.combo_ports.bind("<<ComboboxSelected>>", self._on_device_selected)
        self.combo_ports.bind("<Double-Button-1>", lambda _: self._copy_port_to_clipboard())

        # 2b. Port In-Use Warning Chip (Hidden by default, shown if process locks port)
        self.port_warning_frame = tk.Frame(
            self.main_container,
            bg=COLOR_AMBER_BG,
            highlightthickness=1,
            highlightbackground=COLOR_AMBER_BORDER,
            padx=8,
            pady=3
        )
        self.lbl_port_warning = tk.Label(
            self.port_warning_frame,
            text="⚠ Port in use",
            font=(FONT_UI, 8, "bold"),
            fg=COLOR_AMBER,
            bg=COLOR_AMBER_BG
        )
        self.lbl_port_warning.pack(side=tk.LEFT)

        # 3. Hero Status & Interactive Switch Card
        self.card = tk.Frame(
            self.main_container,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=12,
            pady=12
        )
        self.card.pack(fill=tk.X, pady=(4, 10))

        # Status Line: Glowing Status Pill (Left) + Modern Switch (Right)
        status_line = tk.Frame(self.card, bg=COLOR_SURFACE)
        status_line.pack(fill=tk.X, pady=(0, 6))

        # Status Pill Badge
        self.status_pill = tk.Frame(
            status_line,
            bg=COLOR_AMBER_BG,
            highlightthickness=1,
            highlightbackground=COLOR_AMBER_BORDER,
            padx=8,
            pady=3
        )
        self.status_pill.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(
            self.status_pill,
            text="CHECKING",
            font=(FONT_UI, 9, "bold"),
            fg=COLOR_AMBER,
            bg=COLOR_AMBER_BG
        )
        self.lbl_status.pack()

        # Modern Interactive Toggle Switch
        self.switch = ModernSwitch(
            status_line,
            state=False,
            command=self._on_switch_toggled,
            width=46,
            height=24,
            bg_card=COLOR_SURFACE
        )
        self.switch.pack(side=tk.RIGHT)

        # Description text
        self.lbl_desc = tk.Label(
            self.card,
            text="Checking serial DTR/RTS pin state...",
            font=(FONT_UI, 9),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
            anchor=tk.W
        )
        self.lbl_desc.pack(fill=tk.X, pady=(2, 0))

        # CTA Button inside Card (Only shown if Stock Driver requires install)
        self.btn_stock_install = FlatButton(
            self.card,
            text="Install Kernel Shield",
            command=self.patch_driver,
            bg=COLOR_BLUE_BTN,
            hover_bg=COLOR_BLUE_BTN_HOVER,
            fg="#ffffff",
            font=(FONT_UI, 10, "bold"),
            pady=7,
            border_color=None
        )

        # 4. Secondary Operations Row (Patch / Restore buttons)
        actions_row = tk.Frame(self.main_container, bg=COLOR_BG)
        actions_row.pack(fill=tk.X, pady=(0, 8))

        self.btn_patch = FlatButton(
            actions_row,
            text="Patch Driver",
            command=self.patch_driver,
            font=(FONT_UI, 9),
            padx=6,
            pady=5,
            border_color=COLOR_BORDER
        )
        self.btn_patch.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        # Danger hover for Restore Stock to prevent accidental clicks
        self.btn_restore = FlatButton(
            actions_row,
            text="Restore Stock",
            command=self.restore_driver,
            font=(FONT_UI, 9),
            padx=6,
            pady=5,
            bg=COLOR_BTN_SECONDARY,
            hover_bg=COLOR_RED_BG,
            fg=COLOR_TEXT_MUTED,
            hover_fg=COLOR_RED_TEXT,
            border_color=COLOR_BORDER,
            hover_border_color=COLOR_RED
        )
        self.btn_restore.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # 5. Footer Row (Mini Status + Log Controls)
        footer_row = tk.Frame(self.main_container, bg=COLOR_BG)
        footer_row.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_footer = tk.Label(
            footer_row,
            text="Ready • Space to toggle",
            font=(FONT_UI, 8),
            fg=COLOR_TEXT_DIM,
            bg=COLOR_BG,
            anchor=tk.W
        )
        self.lbl_footer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_clear = tk.Label(
            footer_row,
            text="Clear",
            font=(FONT_UI, 9),
            fg=COLOR_TEXT_DIM,
            bg=COLOR_BG,
            cursor="hand2"
        )
        self.btn_clear.bind("<Button-1>", lambda _: self._clear_log())

        self.btn_log_toggle = tk.Label(
            footer_row,
            text="Log ▸",
            font=(FONT_UI, 9, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_BG,
            cursor="hand2"
        )
        self.btn_log_toggle.pack(side=tk.RIGHT)
        self.btn_log_toggle.bind("<Button-1>", lambda _: self._toggle_log_drawer())

        # 6. Collapsible Log Drawer (Hidden by default)
        self.log_container = tk.Frame(
            self.main_container,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER
        )

        self.txt_log = tk.Text(
            self.log_container,
            height=7,
            wrap=tk.WORD,
            font=(FONT_MONO, 9),
            bg="#060911",
            fg=COLOR_TEXT_MUTED,
            insertbackground="white",
            relief=tk.FLAT,
            padx=8,
            pady=6
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def _copy_port_to_clipboard(self):
        """
        @brief Copy currently selected port name to system clipboard.
        """
        port = self._get_current_port()
        if port:
            self.root.clipboard_clear()
            self.root.clipboard_append(port)
            self._flash_footer(f"Copied {port} to clipboard!")

    def _flash_footer(self, message: str, delay_ms: int = 2500):
        """
        @brief Temporarily display a toast message in the footer bar.
        @param message Text to display.
        @param delay_ms Milliseconds before resetting to default status.
        """
        self.lbl_footer.config(text=message, fg=COLOR_EMERALD)
        self.root.after(delay_ms, lambda: self.lbl_footer.config(text="Ready • Space to toggle", fg=COLOR_TEXT_DIM))

    def _on_space_pressed(self):
        """
        @brief Handle Spacebar press to toggle switch if active.
        """
        if not self.is_operating and self.switch.enabled:
            new_state = not self.switch.state
            self.switch.set_state(new_state)
            self._on_switch_toggled(new_state)

    def _toggle_log_drawer(self):
        """
        @brief Toggle collapsible mini activity log drawer and adjust window height.
        """
        self.log_expanded = not self.log_expanded
        if self.log_expanded:
            self.btn_log_toggle.configure(text="Log ▾", fg=COLOR_TEXT_PRIMARY)
            self.btn_clear.pack(side=tk.RIGHT, padx=(0, 8))
            self.log_container.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            self.root.geometry(f"{self.WINDOW_WIDTH}x{self.HEIGHT_EXPANDED}")
        else:
            self.btn_log_toggle.configure(text="Log ▸", fg=COLOR_TEXT_MUTED)
            self.btn_clear.pack_forget()
            self.log_container.pack_forget()
            self.root.geometry(f"{self.WINDOW_WIDTH}x{self.HEIGHT_COLLAPSED}")

    def _clear_log(self):
        """
        @brief Clear output text in the activity log drawer.
        """
        self.txt_log.delete("1.0", tk.END)

    def log(self, message: str):
        """
        @brief Append a message to the asynchronous log queue.
        @param message Text to display.
        """
        self.log_queue.put(message)

    def _start_log_consumer(self):
        """
        @brief Background poll of log queue to update GUI text safely on main thread.
        """
        def check():
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                self.txt_log.insert(tk.END, msg + "\n")
                self.txt_log.see(tk.END)
            self.root.after(100, check)
        self.root.after(100, check)

    def set_operating(self, operating: bool, status_msg: str = ""):
        """
        @brief Enable or disable controls during an active operation and run spinner.
        @param operating True if busy running a command.
        @param status_msg Status bar description.
        """
        self.is_operating = operating
        state = tk.DISABLED if operating else tk.NORMAL

        self.btn_refresh.set_state(state)
        self.btn_patch.set_state(state)
        self.btn_restore.set_state(state)
        self.btn_stock_install.set_state(state)
        self.switch.set_enabled(not operating and self.current_param_exists)
        self.combo_ports.config(state="readonly" if not operating else tk.DISABLED)

        self.active_task_label = status_msg
        if operating:
            self._animate_spinner()
        else:
            self.lbl_footer.config(text=status_msg if status_msg else "Ready • Space to toggle", fg=COLOR_TEXT_DIM)

    def _animate_spinner(self):
        """
        @brief Animate spinner in footer while an operation is active.
        """
        if self.is_operating:
            frame = self.SPINNER_FRAMES[self.spinner_idx % len(self.SPINNER_FRAMES)]
            self.spinner_idx += 1
            self.lbl_footer.config(text=f"{frame} {self.active_task_label}", fg=COLOR_BLUE_BTN_HOVER)
            self.root.after(100, self._animate_spinner)

    # --------------------------------------------------------------------------
    # Device Scanning & State Resolution
    # --------------------------------------------------------------------------

    def refresh_devices(self):
        """
        @brief Scan available serial ports, check process locks, and query driver parameters.
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

        values = [f"{d['port']} ({d['driver']})" for d in self.devices]
        current_selection = self.combo_ports.get()
        self.combo_ports["values"] = values

        if values:
            if current_selection in values:
                self.combo_ports.set(current_selection)
            else:
                self.combo_ports.current(0)
            self._update_selected_info()
        else:
            self.combo_ports.set("No serial ports detected")
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

    def _on_device_selected(self, _=None):
        self._update_selected_info()

    def _update_selected_info(self):
        """
        @brief Refresh status badge, toggle switch, and port lock warning.
        """
        idx = self.combo_ports.current()
        if idx < 0 or idx >= len(self.devices):
            return

        dev = self.devices[idx]
        driver = dev["driver"]
        port = dev["port"]

        # 1. Check if process is locking port
        lock_pid, lock_name = self._check_port_lock(port)
        if lock_pid:
            self.lbl_port_warning.configure(text=f"⚠ Port in use: {lock_name} (PID {lock_pid})")
            self.port_warning_frame.pack(fill=tk.X, pady=(0, 6), before=self.card)
        else:
            self.port_warning_frame.pack_forget()

        # 2. Check kernel module parameter
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if os.path.isfile(param_file):
            self.current_param_exists = True
            try:
                with open(param_file, "r") as f:
                    val = f.read().strip()
                if val in ("Y", "1"):
                    # Shield Active
                    self.current_protected = True
                    self._set_pill_style(text="● SHIELD ACTIVE", fg=COLOR_EMERALD, bg=COLOR_EMERALD_BG, border=COLOR_EMERALD_BORDER)
                    self.lbl_desc.configure(text="Hardware resets blocked (DTR held HIGH)")
                    self.switch.set_state(True)
                    self.switch.set_enabled(True)
                else:
                    # Shield Inactive
                    self.current_protected = False
                    self._set_pill_style(text="○ SHIELD INACTIVE", fg=COLOR_AMBER, bg=COLOR_AMBER_BG, border=COLOR_AMBER_BORDER)
                    self.lbl_desc.configure(text="Default Linux mode (DTR asserts on connect)")
                    self.switch.set_state(False)
                    self.switch.set_enabled(True)

                self.btn_stock_install.pack_forget()
                self.btn_patch.configure(text="Rebuild Patch")
            except Exception:
                self._set_stock_state(driver)
        else:
            self._set_stock_state(driver)

        self.btn_patch.set_state(tk.NORMAL)
        self.btn_restore.set_state(tk.NORMAL)

    def _set_pill_style(self, text: str, fg: str, bg: str, border: str):
        """
        @brief Update glowing status pill label and container.
        """
        self.status_pill.configure(bg=bg, highlightbackground=border)
        self.lbl_status.configure(text=text, fg=fg, bg=bg)

    def _set_stock_state(self, driver: str):
        """
        @brief Update UI when stock (unpatched) driver is in use.
        @param driver Driver module name (e.g. cp210x).
        """
        self.current_param_exists = False
        self.current_protected = False
        self._set_pill_style(text="△ STOCK DRIVER", fg=COLOR_TEXT_MUTED, bg="#1a2336", border="#2e3d5b")
        self.lbl_desc.configure(text=f"'{driver}' unpatched. Install shield to block resets.")
        self.switch.set_state(False)
        self.switch.set_enabled(False)

        # Show prominent install button inside card
        self.btn_stock_install.pack(fill=tk.X, pady=(10, 0))
        self.btn_patch.configure(text="Patch Driver")

    def _set_no_device_state(self):
        """
        @brief Update UI when no serial hardware is connected.
        """
        self.current_param_exists = False
        self.current_protected = False
        self.port_warning_frame.pack_forget()
        self._set_pill_style(text="NO DEVICE", fg=COLOR_TEXT_DIM, bg="#131926", border="#1e293b")
        self.lbl_desc.configure(text="Connect a USB-UART adapter or gimbal.")
        self.switch.set_state(False)
        self.switch.set_enabled(False)
        self.btn_stock_install.pack_forget()
        self.btn_patch.set_state(tk.DISABLED)
        self.btn_restore.set_state(tk.DISABLED)

    def _schedule_auto_refresh(self):
        """
        @brief Periodically poll devices every 3 seconds if not operating.
        """
        if not self.is_operating:
            self.refresh_devices()
        self.root.after(3000, self._schedule_auto_refresh)

    def _get_current_driver(self) -> str:
        """
        @brief Retrieve driver module name for currently selected device.
        @return Driver module string (defaults to cp210x).
        """
        idx = self.combo_ports.current()
        if idx >= 0 and idx < len(self.devices):
            return self.devices[idx]["driver"]
        return "cp210x"

    def _get_current_port(self) -> str:
        """
        @brief Retrieve serial port path (e.g. /dev/ttyUSB0).
        """
        idx = self.combo_ports.current()
        if idx >= 0 and idx < len(self.devices):
            return self.devices[idx]["port"]
        return ""

    # --------------------------------------------------------------------------
    # Asynchronous Execution via Core Script
    # --------------------------------------------------------------------------

    def _run_core_command(self, args: list, task_name: str, on_complete=None):
        """
        @brief Run uart_kernel_patch.sh asynchronously via pkexec.
        @param args CLI arguments.
        @param task_name Display label.
        @param on_complete Optional callback upon completion.
        """
        if self.is_operating:
            return

        # Auto-expand log on operations so user sees progress
        if not self.log_expanded:
            self._toggle_log_drawer()

        self.set_operating(True, task_name)
        self.log(f"\n[ACTION] {task_name}")

        def worker():
            cmd = ["pkexec", CORE_SCRIPT] + args
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                for line in proc.stdout:
                    clean = self._strip_ansi(line.rstrip())
                    self.log(clean)

                proc.wait()
                rc = proc.returncode

                if rc == 0:
                    self.log(f"[DONE] {task_name} succeeded.")
                    msg = f"✓ {task_name} succeeded."
                elif rc in (126, 127):
                    self.log(f"[CANCEL] {task_name} cancelled by user.")
                    msg = "Operation cancelled."
                else:
                    self.log(f"[FAIL] {task_name} failed (exit code: {rc}).")
                    msg = f"Failed (exit code {rc})."

            except Exception as e:
                self.log(f"[ERROR] {e}")
                msg = f"Error: {e}"

            def finish():
                self.set_operating(False, msg)
                self.refresh_devices()
                if on_complete:
                    on_complete()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _strip_ansi(self, text: str) -> str:
        """
        @brief Strip terminal ANSI color escape codes from string.
        @param text Raw string.
        @return Cleaned plain string.
        """
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    # --------------------------------------------------------------------------
    # Action Handlers
    # --------------------------------------------------------------------------

    def _on_switch_toggled(self, new_state: bool):
        """
        @brief Handle user toggling the Modern Switch.
        @param new_state True for Shield ON, False for Shield OFF.
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
        confirm = messagebox.askyesno(
            "Install Patch",
            f"Build and install DTR/RTS reset shield for '{driver}'?\n\n"
            "This will download, patch, and install the kernel driver module.",
            parent=self.root
        )
        if not confirm:
            return

        self._run_core_command(["patch", driver, "-y"], f"Patching {driver}")

    def restore_driver(self):
        """
        @brief Trigger driver restore to stock Ubuntu version.
        """
        driver = self._get_current_driver()
        confirm = messagebox.askyesno(
            "Restore Stock Driver",
            f"Restore original factory driver for '{driver}'?\n\n"
            "Warning: This will remove reset protection and restore standard Ubuntu DTR/RTS behavior.",
            parent=self.root
        )
        if not confirm:
            return

        self._run_core_command(["restore", driver, "-y"], f"Restoring {driver}")


def main():
    if not os.path.isfile(CORE_SCRIPT):
        print(f"Error: Missing core script: {CORE_SCRIPT}")
        sys.exit(1)

    root = tk.Tk()
    app = UARTShieldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
