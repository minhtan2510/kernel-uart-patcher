#!/usr/bin/env python3
"""
UART DTR/RTS Shield — Modern Minimalist Control Panel.

A lightweight, zero-dependency utility to prevent Linux kernel
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
from tkinter import ttk, messagebox

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPT = os.path.join(SCRIPT_DIR, "uart_kernel_patch.sh")

# Minimalist Dark Palette (Tailwind / Slate / Zinc inspired)
COLOR_BG = "#0b0f17"
COLOR_CARD = "#141c2b"
COLOR_CARD_BORDER = "#222f46"
COLOR_TEXT_PRIMARY = "#f8fafc"
COLOR_TEXT_SECONDARY = "#94a3b8"
COLOR_TEXT_MUTED = "#64748b"

COLOR_GREEN = "#10b981"
COLOR_GREEN_BG = "#064e3b"
COLOR_AMBER = "#f59e0b"
COLOR_AMBER_BG = "#78350f"
COLOR_RED = "#ef4444"
COLOR_BLUE = "#3b82f6"
COLOR_BLUE_HOVER = "#2563eb"
COLOR_BTN_DARK = "#1e293b"
COLOR_BTN_DARK_HOVER = "#334155"


class ModernButton(tk.Label):
    """Clean flat hoverable button with minimalist modern styling."""
    def __init__(self, parent, text, command=None, bg=COLOR_BTN_DARK, hover_bg=COLOR_BTN_DARK_HOVER,
                 fg=COLOR_TEXT_PRIMARY, font=("Inter", 9, "bold"), padx=14, pady=8, state=tk.NORMAL, **kwargs):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font,
                         padx=padx, pady=pady, cursor="hand2", **kwargs)
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.command = command
        self.state_val = state

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
        self.state_val = state
        if state == tk.DISABLED:
            self.configure(cursor="arrow", fg=COLOR_TEXT_MUTED, bg="#161e2e")
        else:
            self.configure(cursor="hand2", fg=COLOR_TEXT_PRIMARY, bg=self.default_bg)

    def set_theme(self, bg, hover_bg, fg=COLOR_TEXT_PRIMARY):
        self.default_bg = bg
        self.hover_bg = hover_bg
        if self.state_val == tk.NORMAL:
            self.configure(bg=bg, fg=fg)


class UARTShieldApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("UART Shield")
        self.root.geometry("620x640")
        self.root.minsize(560, 540)
        self.root.configure(bg=COLOR_BG)

        # State
        self.devices = []
        self.log_queue = queue.Queue()
        self.is_operating = False
        self.log_expanded = False
        self.current_protected = False

        self._build_ui()
        self._start_log_consumer()

        # Initial device scan & auto refresh
        self.refresh_devices()
        self._schedule_auto_refresh()

    def _build_ui(self):
        # Top Header (Minimalist & Flat)
        header_frame = tk.Frame(self.root, bg=COLOR_BG, padx=24, pady=18)
        header_frame.pack(fill=tk.X)

        title_row = tk.Frame(header_frame, bg=COLOR_BG)
        title_row.pack(fill=tk.X)

        lbl_title = tk.Label(
            title_row,
            text="UART Shield",
            font=("Inter", 14, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_BG
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_tag = tk.Label(
            title_row,
            text="KERNEL LEVEL",
            font=("Inter", 8, "bold"),
            fg=COLOR_BLUE,
            bg="#172554",
            padx=6,
            pady=2
        )
        lbl_tag.pack(side=tk.LEFT, padx=(10, 0))

        lbl_subtitle = tk.Label(
            header_frame,
            text="Hardware reset protection for connected serial devices and gimbals",
            font=("Inter", 9),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_BG
        )
        lbl_subtitle.pack(anchor=tk.W, pady=(4, 0))

        # Main Container
        main_box = tk.Frame(self.root, bg=COLOR_BG, padx=24)
        main_box.pack(fill=tk.BOTH, expand=True)

        # --- Card 1: Port Selector ---
        port_card = tk.Frame(main_box, bg=COLOR_CARD, highlightthickness=1,
                             highlightbackground=COLOR_CARD_BORDER, padx=16, pady=14)
        port_card.pack(fill=tk.X, pady=(0, 12))

        lbl_port_section = tk.Label(
            port_card,
            text="ACTIVE PORT",
            font=("Inter", 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD
        )
        lbl_port_section.pack(anchor=tk.W, pady=(0, 8))

        port_row = tk.Frame(port_card, bg=COLOR_CARD)
        port_row.pack(fill=tk.X)

        # Styled combobox
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=COLOR_CARD,
                        background=COLOR_BTN_DARK,
                        foreground=COLOR_TEXT_PRIMARY,
                        darkcolor=COLOR_CARD_BORDER,
                        lightcolor=COLOR_CARD_BORDER,
                        arrowcolor=COLOR_TEXT_SECONDARY)

        self.combo_ports = ttk.Combobox(port_row, state="readonly", font=("Inter", 10), style="TCombobox")
        self.combo_ports.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.combo_ports.bind("<<ComboboxSelected>>", self._on_device_selected)

        self.btn_refresh = ModernButton(
            port_row,
            text="↻ Refresh",
            command=self.refresh_devices,
            font=("Inter", 9),
            padx=12,
            pady=6
        )
        self.btn_refresh.pack(side=tk.RIGHT, padx=(10, 0))

        # --- Card 2: Protection Status & Primary Toggle ---
        self.status_card = tk.Frame(main_box, bg=COLOR_CARD, highlightthickness=1,
                                    highlightbackground=COLOR_CARD_BORDER, padx=18, pady=16)
        self.status_card.pack(fill=tk.X, pady=(0, 12))

        lbl_status_section = tk.Label(
            self.status_card,
            text="PROTECTION STATUS",
            font=("Inter", 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD
        )
        lbl_status_section.pack(anchor=tk.W, pady=(0, 6))

        # Indicator badge row
        badge_row = tk.Frame(self.status_card, bg=COLOR_CARD)
        badge_row.pack(fill=tk.X, pady=(0, 12))

        self.lbl_dot = tk.Label(badge_row, text="●", font=("Inter", 12), fg=COLOR_AMBER, bg=COLOR_CARD)
        self.lbl_dot.pack(side=tk.LEFT)

        self.lbl_status_text = tk.Label(
            badge_row,
            text="Checking status...",
            font=("Inter", 11, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD
        )
        self.lbl_status_text.pack(side=tk.LEFT, padx=(6, 0))

        self.lbl_status_sub = tk.Label(
            self.status_card,
            text="Driver behavior and DTR/RTS assertion control.",
            font=("Inter", 9),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_CARD
        )
        self.lbl_status_sub.pack(anchor=tk.W, pady=(0, 14))

        # Big Action Button (Toggle)
        self.btn_main_toggle = ModernButton(
            self.status_card,
            text="Enable Protection",
            command=self._on_main_toggle_clicked,
            bg=COLOR_BLUE,
            hover_bg=COLOR_BLUE_HOVER,
            fg="#ffffff",
            font=("Inter", 10, "bold"),
            pady=10
        )
        self.btn_main_toggle.pack(fill=tk.X)

        # --- Card 3: Kernel Module Management ---
        mgmt_card = tk.Frame(main_box, bg=COLOR_CARD, highlightthickness=1,
                             highlightbackground=COLOR_CARD_BORDER, padx=16, pady=14)
        mgmt_card.pack(fill=tk.X, pady=(0, 12))

        lbl_mgmt_section = tk.Label(
            mgmt_card,
            text="KERNEL DRIVER OPERATIONS",
            font=("Inter", 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD
        )
        lbl_mgmt_section.pack(anchor=tk.W, pady=(0, 10))

        mgmt_btns = tk.Frame(mgmt_card, bg=COLOR_CARD)
        mgmt_btns.pack(fill=tk.X)

        self.btn_patch = ModernButton(
            mgmt_btns,
            text="Install Kernel Patch",
            command=self.patch_driver,
            font=("Inter", 9),
            pady=8
        )
        self.btn_patch.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.btn_restore = ModernButton(
            mgmt_btns,
            text="Restore Stock Driver",
            command=self.restore_driver,
            font=("Inter", 9),
            pady=8
        )
        self.btn_restore.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        # --- Section 4: Minimal Collapsible Log Drawer ---
        log_header_frame = tk.Frame(main_box, bg=COLOR_BG)
        log_header_frame.pack(fill=tk.X, pady=(4, 6))

        self.btn_log_toggle = tk.Label(
            log_header_frame,
            text="▶  Activity Log",
            font=("Inter", 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_BG,
            cursor="hand2"
        )
        self.btn_log_toggle.pack(side=tk.LEFT)
        self.btn_log_toggle.bind("<Button-1>", lambda _: self._toggle_log_drawer())

        self.log_container = tk.Frame(main_box, bg=COLOR_CARD, highlightthickness=1,
                                      highlightbackground=COLOR_CARD_BORDER)

        self.txt_log = tk.Text(
            self.log_container,
            height=6,
            wrap=tk.WORD,
            font=("DejaVu Sans Mono", 8),
            bg="#080c14",
            fg="#94a3b8",
            insertbackground="white",
            relief=tk.FLAT,
            padx=10,
            pady=8
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Status Bar
        self.status_bar = tk.Label(
            self.root,
            text="Ready",
            font=("Inter", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_BG,
            padx=24,
            pady=6,
            anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _toggle_log_drawer(self):
        self.log_expanded = not self.log_expanded
        if self.log_expanded:
            self.btn_log_toggle.configure(text="▼  Activity Log", fg=COLOR_TEXT_PRIMARY)
            self.log_container.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        else:
            self.btn_log_toggle.configure(text="▶  Activity Log", fg=COLOR_TEXT_MUTED)
            self.log_container.pack_forget()

    def log(self, message: str):
        self.log_queue.put(message)

    def _start_log_consumer(self):
        def check():
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                self.txt_log.insert(tk.END, msg + "\n")
                self.txt_log.see(tk.END)
            self.root.after(100, check)
        self.root.after(100, check)

    def set_operating(self, operating: bool, status_msg: str = ""):
        self.is_operating = operating
        state = tk.DISABLED if operating else tk.NORMAL

        self.btn_refresh.set_state(state)
        self.btn_main_toggle.set_state(state)
        self.btn_patch.set_state(state)
        self.btn_restore.set_state(state)
        self.combo_ports.config(state="readonly" if not operating else tk.DISABLED)

        if status_msg:
            self.status_bar.config(text=status_msg)

    # ==========================================================================
    # Device Scanning & State Evaluation
    # ==========================================================================

    def refresh_devices(self):
        if self.is_operating:
            return

        self.devices = []
        try:
            ports = [f"/dev/{f}" for f in os.listdir("/dev") if f.startswith("ttyUSB") or f.startswith("ttyACM")]
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
            self.combo_ports.set("No serial devices detected")
            self.lbl_dot.configure(fg=COLOR_TEXT_MUTED)
            self.lbl_status_text.configure(text="No Device Connected", fg=COLOR_TEXT_MUTED)
            self.lbl_status_sub.configure(text="Connect a USB-UART adapter or gimbal to begin.")
            self.btn_main_toggle.set_state(tk.DISABLED)
            self.btn_patch.set_state(tk.DISABLED)
            self.btn_restore.set_state(tk.DISABLED)

    def _on_device_selected(self, _=None):
        self._update_selected_info()

    def _update_selected_info(self):
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
                    # Protected State
                    self.current_protected = True
                    self.lbl_dot.configure(fg=COLOR_GREEN)
                    self.lbl_status_text.configure(text="PROTECTED — Reset Blocked", fg=COLOR_GREEN)
                    self.lbl_status_sub.configure(
                        text=f"Driver '{driver}' locks DTR/RTS High (3.3V). Device will not reset."
                    )
                    self.btn_main_toggle.configure(text="Disable Protection (Restore Default DTR/RTS)")
                    self.btn_main_toggle.set_theme(bg=COLOR_BTN_DARK, hover_bg=COLOR_BTN_DARK_HOVER, fg=COLOR_TEXT_PRIMARY)
                else:
                    # Unprotected State (Toggle OFF)
                    self.current_protected = False
                    self.lbl_dot.configure(fg=COLOR_AMBER)
                    self.lbl_status_text.configure(text="UNPROTECTED — Default Kernel Mode", fg=COLOR_AMBER)
                    self.lbl_status_sub.configure(
                        text=f"Driver '{driver}' controls DTR/RTS normally. Connecting may reset device."
                    )
                    self.btn_main_toggle.configure(text="Enable Protection (Block Reset)")
                    self.btn_main_toggle.set_theme(bg=COLOR_BLUE, hover_bg=COLOR_BLUE_HOVER, fg="#ffffff")

                self.btn_main_toggle.set_state(tk.NORMAL)
            except Exception:
                self._set_stock_state(driver)
        else:
            self._set_stock_state(driver)

        self.btn_patch.set_state(tk.NORMAL)
        self.btn_restore.set_state(tk.NORMAL)

    def _set_stock_state(self, driver: str):
        self.current_protected = False
        self.lbl_dot.configure(fg=COLOR_AMBER)
        self.lbl_status_text.configure(text="STOCK DRIVER — Patch Not Installed", fg=COLOR_AMBER)
        self.lbl_status_sub.configure(
            text=f"Kernel driver '{driver}' is unpatched. Click below to install protection."
        )
        self.btn_main_toggle.configure(text="Install & Enable Protection")
        self.btn_main_toggle.set_theme(bg=COLOR_BLUE, hover_bg=COLOR_BLUE_HOVER, fg="#ffffff")
        self.btn_main_toggle.set_state(tk.NORMAL)

    def _schedule_auto_refresh(self):
        if not self.is_operating:
            self.refresh_devices()
        self.root.after(3000, self._schedule_auto_refresh)

    def _get_current_driver(self) -> str:
        idx = self.combo_ports.current()
        if idx >= 0 and idx < len(self.devices):
            return self.devices[idx]["driver"]
        return "cp210x"

    # ==========================================================================
    # Asynchronous Core Execution
    # ==========================================================================

    def _run_core_command(self, args: list, task_name: str, on_complete=None):
        if self.is_operating:
            return

        self.set_operating(True, f"Running: {task_name}...")
        self.log(f"\n[ACTION: {task_name}]")

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
                    clean_line = self._strip_ansi(line.rstrip())
                    self.log(clean_line)

                proc.wait()
                rc = proc.returncode

                if rc == 0:
                    self.log(f"[SUCCESS: {task_name}]")
                    msg = f"{task_name} completed."
                elif rc in (126, 127):
                    self.log(f"[CANCELLED: {task_name}]")
                    msg = "Operation cancelled."
                else:
                    self.log(f"[FAILED: {task_name} (code: {rc})]")
                    msg = f"{task_name} failed. Check log for details."

            except Exception as e:
                self.log(f"Execution error: {e}")
                msg = f"Error: {e}"

            def finish():
                self.set_operating(False, msg)
                self.refresh_devices()
                if on_complete:
                    on_complete()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _strip_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    # ==========================================================================
    # Action Handlers
    # ==========================================================================

    def _on_main_toggle_clicked(self):
        driver = self._get_current_driver()
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"

        if not os.path.isfile(param_file):
            # Not yet patched -> install patch
            self.patch_driver()
        else:
            # Already patched -> toggle live between 1 and 0
            new_val = 0 if self.current_protected else 1
            task = "Block Reset" if new_val == 1 else "Allow Default DTR/RTS"
            self._run_core_command(["toggle", driver, str(new_val)], task)

    def patch_driver(self):
        driver = self._get_current_driver()
        confirm = messagebox.askyesno(
            "Install Kernel Patch",
            f"Install Deep Patch for driver '{driver}'?\n\n"
            "This compiles and installs an updated driver module that prevents DTR/RTS reset assertions.",
            parent=self.root
        )
        if not confirm:
            return

        self._run_core_command(["patch", driver, "-y"], f"Patching {driver}")

    def restore_driver(self):
        driver = self._get_current_driver()
        confirm = messagebox.askyesno(
            "Restore Stock Driver",
            f"Restore original Ubuntu stock driver for '{driver}'?\n\n"
            "This reverts any kernel modifications back to factory defaults.",
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
