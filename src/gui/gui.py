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
COLOR_EMERALD_BTN = "#059669"  # Emerald 600 primary action
COLOR_EMERALD_BTN_HOVER = "#10b981"

COLOR_AMBER = "#f59e0b"        # Amber 500 (Unprotected warning)
COLOR_AMBER_BG = "#451a03"

COLOR_BLUE_BTN = "#2563eb"     # Blue 600
COLOR_BLUE_BTN_HOVER = "#3b82f6"

COLOR_BTN_SECONDARY = "#192235"
COLOR_BTN_SECONDARY_HOVER = "#24314c"
COLOR_BTN_SECONDARY_BORDER = "#27354f"


class FlatButton(tk.Label):
    """
    @brief Minimalist flat button with hover feedback and solid borders.
    """
    def __init__(
        self,
        parent,
        text: str,
        command=None,
        bg=COLOR_BTN_SECONDARY,
        hover_bg=COLOR_BTN_SECONDARY_HOVER,
        fg=COLOR_TEXT_PRIMARY,
        font=(FONT_UI, 9, "bold"),
        padx=10,
        pady=6,
        state=tk.NORMAL,
        border_color=COLOR_BORDER,
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
        self.command = command
        self.state_val = state
        self.default_fg = fg

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _):
        if self.state_val == tk.NORMAL:
            self.configure(bg=self.hover_bg)

    def _on_leave(self, _):
        if self.state_val == tk.NORMAL:
            self.configure(bg=self.default_bg)

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
            self.configure(cursor="arrow", fg=COLOR_TEXT_DIM, bg="#0d131f")
        else:
            self.configure(cursor="hand2", fg=self.default_fg, bg=self.default_bg)

    def set_theme(self, bg: str, hover_bg: str, fg=COLOR_TEXT_PRIMARY, border_color=None):
        """
        @brief Reconfigure button theme dynamically.
        @param bg Normal background color.
        @param hover_bg Background color on hover.
        @param fg Text color.
        @param border_color Optional border highlight.
        """
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.default_fg = fg
        if border_color is not None:
            self.configure(highlightbackground=border_color)
        if self.state_val == tk.NORMAL:
            self.configure(bg=bg, fg=fg)


class UARTShieldApp:
    """
    @brief Ultra-compact modern minimalist control GUI for serial DTR/RTS reset shield.
    """
    WINDOW_WIDTH = 360
    HEIGHT_COLLAPSED = 285
    HEIGHT_EXPANDED = 435

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

        self._init_theme()
        self._build_ui()
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

    def _build_ui(self):
        """
        @brief Construct ultra-compact minimalist interface.
        """
        self.main_container = tk.Frame(self.root, bg=COLOR_BG, padx=14, pady=12)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # 1. Header Row (App Title + Linux Pill + Refresh Button)
        header_row = tk.Frame(self.main_container, bg=COLOR_BG)
        header_row.pack(fill=tk.X, pady=(0, 10))

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

        # 2. Port Selector Dropdown (Clean, high-legibility font)
        port_row = tk.Frame(self.main_container, bg=COLOR_BG)
        port_row.pack(fill=tk.X, pady=(0, 10))

        self.combo_ports = ttk.Combobox(
            port_row,
            state="readonly",
            font=(FONT_UI, 10),
            style="Compact.TCombobox"
        )
        self.combo_ports.pack(fill=tk.X, ipady=4)
        self.combo_ports.bind("<<ComboboxSelected>>", self._on_device_selected)

        # 3. Status & Hero Action Card
        self.card = tk.Frame(
            self.main_container,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=12,
            pady=12
        )
        self.card.pack(fill=tk.X, pady=(0, 10))

        status_line = tk.Frame(self.card, bg=COLOR_SURFACE)
        status_line.pack(fill=tk.X, pady=(0, 3))

        self.lbl_dot = tk.Label(
            status_line,
            text="●",
            font=(FONT_UI, 11),
            fg=COLOR_AMBER,
            bg=COLOR_SURFACE
        )
        self.lbl_dot.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(
            status_line,
            text="Detecting driver...",
            font=(FONT_UI, 10, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_SURFACE
        )
        self.lbl_status.pack(side=tk.LEFT, padx=(6, 0))

        self.lbl_desc = tk.Label(
            self.card,
            text="Checking serial DTR/RTS pin state...",
            font=(FONT_UI, 9),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
            anchor=tk.W
        )
        self.lbl_desc.pack(fill=tk.X, pady=(0, 10))

        # Primary Toggle CTA Button
        self.btn_main = FlatButton(
            self.card,
            text="Enable Shield",
            command=self._on_main_toggle_clicked,
            bg=COLOR_EMERALD_BTN,
            hover_bg=COLOR_EMERALD_BTN_HOVER,
            fg="#ffffff",
            font=(FONT_UI, 10, "bold"),
            pady=8,
            border_color=None
        )
        self.btn_main.pack(fill=tk.X)

        # 4. Secondary Quick Actions (Compact 2-Pill Bar)
        actions_row = tk.Frame(self.main_container, bg=COLOR_BG)
        actions_row.pack(fill=tk.X, pady=(0, 10))

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

        self.btn_restore = FlatButton(
            actions_row,
            text="Restore Stock",
            command=self.restore_driver,
            font=(FONT_UI, 9),
            padx=6,
            pady=5,
            border_color=COLOR_BORDER
        )
        self.btn_restore.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # 5. Footer Row (Mini Status + Log Controls)
        footer_row = tk.Frame(self.main_container, bg=COLOR_BG)
        footer_row.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_footer = tk.Label(
            footer_row,
            text="Ready",
            font=(FONT_UI, 9),
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
        @brief Enable or disable controls during an active operation.
        @param operating True if busy running a command.
        @param status_msg Status bar description.
        """
        self.is_operating = operating
        state = tk.DISABLED if operating else tk.NORMAL

        self.btn_refresh.set_state(state)
        self.btn_main.set_state(state)
        self.btn_patch.set_state(state)
        self.btn_restore.set_state(state)
        self.combo_ports.config(state="readonly" if not operating else tk.DISABLED)

        if status_msg:
            self.lbl_footer.config(text=status_msg)

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
            self.lbl_dot.configure(fg=COLOR_TEXT_DIM)
            self.lbl_status.configure(text="No Device", fg=COLOR_TEXT_DIM)
            self.lbl_desc.configure(text="Connect a USB-UART adapter or gimbal.")
            self.btn_main.configure(text="No Device")
            self.btn_main.set_state(tk.DISABLED)
            self.btn_patch.set_state(tk.DISABLED)
            self.btn_restore.set_state(tk.DISABLED)

    def _on_device_selected(self, _=None):
        self._update_selected_info()

    def _update_selected_info(self):
        """
        @brief Refresh status badge and action button based on sysfs driver parameter.
        """
        idx = self.combo_ports.current()
        if idx < 0 or idx >= len(self.devices):
            return

        dev = self.devices[idx]
        driver = dev["driver"]
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if os.path.isfile(param_file):
            try:
                with open(param_file, "r") as f:
                    val = f.read().strip()
                if val in ("Y", "1"):
                    # Shield Active (Reset Blocked)
                    self.current_protected = True
                    self.lbl_dot.configure(fg=COLOR_EMERALD)
                    self.lbl_status.configure(text="Shield Active", fg=COLOR_EMERALD)
                    self.lbl_desc.configure(text="DTR/RTS locked HIGH (resets blocked)")
                    self.btn_main.configure(text="Disable Shield")
                    self.btn_main.set_theme(
                        bg=COLOR_BTN_SECONDARY,
                        hover_bg=COLOR_BTN_SECONDARY_HOVER,
                        fg=COLOR_TEXT_PRIMARY,
                        border_color=COLOR_BORDER
                    )
                else:
                    # Unprotected (Normal Kernel Assertions)
                    self.current_protected = False
                    self.lbl_dot.configure(fg=COLOR_AMBER)
                    self.lbl_status.configure(text="Shield Inactive", fg=COLOR_AMBER)
                    self.lbl_desc.configure(text="Kernel asserts DTR/RTS on connect")
                    self.btn_main.configure(text="Enable Shield")
                    self.btn_main.set_theme(
                        bg=COLOR_EMERALD_BTN,
                        hover_bg=COLOR_EMERALD_BTN_HOVER,
                        fg="#ffffff",
                        border_color=None
                    )

                self.btn_main.set_state(tk.NORMAL)
            except Exception:
                self._set_stock_state(driver)
        else:
            self._set_stock_state(driver)

        self.btn_patch.set_state(tk.NORMAL)
        self.btn_restore.set_state(tk.NORMAL)

    def _set_stock_state(self, driver: str):
        """
        @brief Update UI when stock (unpatched) driver is in use.
        @param driver Driver module name (e.g. cp210x).
        """
        self.current_protected = False
        self.lbl_dot.configure(fg=COLOR_AMBER)
        self.lbl_status.configure(text="Stock Driver", fg=COLOR_AMBER)
        self.lbl_desc.configure(text=f"'{driver}' unpatched. Install patch to shield.")
        self.btn_main.configure(text="Install & Shield")
        self.btn_main.set_theme(
            bg=COLOR_BLUE_BTN,
            hover_bg=COLOR_BLUE_BTN_HOVER,
            fg="#ffffff",
            border_color=None
        )
        self.btn_main.set_state(tk.NORMAL)

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

        self.set_operating(True, f"{task_name}...")
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
                    msg = f"{task_name} done."
                elif rc in (126, 127):
                    self.log(f"[CANCEL] {task_name} cancelled by user.")
                    msg = "Cancelled."
                else:
                    self.log(f"[FAIL] {task_name} failed (exit code: {rc}).")
                    msg = f"{task_name} failed."

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

    def _on_main_toggle_clicked(self):
        """
        @brief Handle clicks on the hero action button.
        """
        driver = self._get_current_driver()
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if not os.path.isfile(param_file):
            self.patch_driver()
        else:
            new_val = 0 if self.current_protected else 1
            task = "Shield Active" if new_val == 1 else "Shield Inactive"
            self._run_core_command(["toggle", driver, str(new_val)], f"Set {task}")

    def patch_driver(self):
        """
        @brief Trigger driver patch installation.
        """
        driver = self._get_current_driver()
        confirm = messagebox.askyesno(
            "Install Patch",
            f"Build and install DTR/RTS reset shield for '{driver}'?",
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
            "Restore Stock",
            f"Restore original factory driver for '{driver}'?",
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
