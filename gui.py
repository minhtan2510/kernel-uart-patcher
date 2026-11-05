#!/usr/bin/env python3
"""
GUI Dashboard for Linux UART DTR/RTS Control Panel.

Built with Python Tkinter (standard library, zero dependencies).
Interacts with the underlying core tool: uart_kernel_patch.sh
"""

import os
import sys
import subprocess
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPT = os.path.join(SCRIPT_DIR, "uart_kernel_patch.sh")


class UARTControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("UART DTR/RTS Control Panel (Gimbal Reset Fix)")
        self.root.geometry("720x620")
        self.root.minsize(640, 520)

        # State
        self.devices = []
        self.selected_device = None
        self.log_queue = queue.Queue()
        self.is_operating = False

        self._init_style()
        self._build_ui()
        self._start_log_consumer()

        # Initial scan & auto-refresh poll
        self.refresh_devices()
        self._schedule_auto_refresh()

    def _init_style(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Configure custom colors
        self.style.configure(".", font=("Sans", 10))
        self.style.configure("Header.TLabel", font=("Sans", 12, "bold"))
        self.style.configure("SubHeader.TLabel", font=("Sans", 10, "bold"), foreground="#333333")
        self.style.configure("BadgeGreen.TLabel", font=("Sans", 10, "bold"), foreground="#1e7e34")
        self.style.configure("BadgeRed.TLabel", font=("Sans", 10, "bold"), foreground="#bd2130")
        self.style.configure("BadgeYellow.TLabel", font=("Sans", 10, "bold"), foreground="#d39e00")

    def _build_ui(self):
        # Top banner
        banner_frame = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        banner_frame.pack(fill=tk.X)

        title = ttk.Label(
            banner_frame,
            text="Trình Quản Lý DTR/RTS Cổng Serial (Kernel Deep Patch)",
            style="Header.TLabel"
        )
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            banner_frame,
            text="Ngăn chặn Ubuntu Kernel và Ứng dụng tự động kéo chân Reset Gimbal / MCU khi kết nối",
            foreground="#666666"
        )
        subtitle.pack(anchor=tk.W, pady=(2, 0))

        # Main content container
        main_frame = ttk.Frame(self.root, padding=(16, 0, 16, 12))
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Section 1: Device List & Detection ---
        dev_group = ttk.LabelFrame(main_frame, text=" Thiết Bị USB-UART Đang Kết Nối ", padding=12)
        dev_group.pack(fill=tk.X, pady=(0, 10))

        top_row = ttk.Frame(dev_group)
        top_row.pack(fill=tk.X)

        ttk.Label(top_row, text="Cổng kết nối:").pack(side=tk.LEFT)
        self.dev_combo = ttk.Combobox(top_row, state="readonly", width=36)
        self.dev_combo.pack(side=tk.LEFT, padx=(8, 12))
        self.dev_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        self.btn_refresh = ttk.Button(top_row, text="Làm Mới (F5)", command=self.refresh_devices)
        self.btn_refresh.pack(side=tk.LEFT)

        # Status badge frame
        self.status_frame = ttk.Frame(dev_group)
        self.status_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(self.status_frame, text="Driver Kernel:", style="SubHeader.TLabel").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.lbl_driver = ttk.Label(self.status_frame, text="Chưa xác định", foreground="#666666")
        self.lbl_driver.grid(row=0, column=1, sticky=tk.W, padx=8, pady=2)

        ttk.Label(self.status_frame, text="Bản vá (Patch):", style="SubHeader.TLabel").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.lbl_patch_status = ttk.Label(self.status_frame, text="Chưa xác định", style="BadgeYellow.TLabel")
        self.lbl_patch_status.grid(row=1, column=1, sticky=tk.W, padx=8, pady=2)

        ttk.Label(self.status_frame, text="Chống Reset DTR:", style="SubHeader.TLabel").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.lbl_dtr_status = ttk.Label(self.status_frame, text="Chưa xác định", style="BadgeYellow.TLabel")
        self.lbl_dtr_status.grid(row=2, column=1, sticky=tk.W, padx=8, pady=2)

        # --- Section 2: Quick Control (Live Toggle) ---
        toggle_group = ttk.LabelFrame(main_frame, text=" Điều Khiển Live Nhanh (Không Cần Reload Driver) ", padding=12)
        toggle_group.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            toggle_group,
            text="Chuyển đổi trạng thái trực tiếp trong sysfs ngay tức thì:",
            foreground="#555555"
        ).pack(anchor=tk.W, pady=(0, 8))

        btn_box = ttk.Frame(toggle_group)
        btn_box.pack(fill=tk.X)

        self.btn_toggle_block = ttk.Button(
            btn_box,
            text="🛡️ Bật Chặn Reset (DTR/RTS OFF)",
            command=lambda: self.toggle_dtr(1)
        )
        self.btn_toggle_block.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.btn_toggle_allow = ttk.Button(
            btn_box,
            text="⚡ Mặc Định Kernel (DTR/RTS ON)",
            command=lambda: self.toggle_dtr(0)
        )
        self.btn_toggle_allow.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        # --- Section 3: Kernel Module Management ---
        kernel_group = ttk.LabelFrame(main_frame, text=" Quản Lý Driver Kernel ", padding=12)
        kernel_group.pack(fill=tk.X, pady=(0, 10))

        k_btn_box = ttk.Frame(kernel_group)
        k_btn_box.pack(fill=tk.X)

        self.btn_patch = ttk.Button(
            k_btn_box,
            text="🔧 Cài Đặt Deep Patch (Vào Driver)",
            command=self.patch_driver
        )
        self.btn_patch.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.btn_restore = ttk.Button(
            k_btn_box,
            text="↺ Khôi Phục Driver Gốc Ubuntu",
            command=self.restore_driver
        )
        self.btn_restore.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        # --- Section 4: Output Log Viewer ---
        log_group = ttk.LabelFrame(main_frame, text=" Nhật Ký Hoạt Động (Terminal Log) ", padding=8)
        log_group.pack(fill=tk.BOTH, expand=True)

        self.txt_log = scrolledtext.ScrolledText(
            log_group,
            height=7,
            wrap=tk.WORD,
            font=("Monospace", 9),
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="white"
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Status Bar
        self.status_bar = ttk.Label(self.root, text="Sẵn sàng", padding=(16, 4), relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.root.bind("<F5>", lambda e: self.refresh_devices())

    def log(self, message: str):
        self.log_queue.put(message)

    def _start_log_consumer(self):
        def check_queue():
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                self.txt_log.insert(tk.END, msg + "\n")
                self.txt_log.see(tk.END)
            self.root.after(100, check_queue)

        self.root.after(100, check_queue)

    def set_operating(self, operating: bool, status_msg: str = ""):
        self.is_operating = operating
        state = tk.DISABLED if operating else tk.NORMAL

        self.btn_refresh.config(state=state)
        self.btn_toggle_block.config(state=state)
        self.btn_toggle_allow.config(state=state)
        self.btn_patch.config(state=state)
        self.btn_restore.config(state=state)
        self.dev_combo.config(state="readonly" if not operating else tk.DISABLED)

        if status_msg:
            self.status_bar.config(text=status_msg)

    # ==========================================================================
    # Detection & Device Parsing
    # ==========================================================================

    def refresh_devices(self):
        if self.is_operating:
            return

        self.devices = []
        try:
            # Scan serial ports in /dev/
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
            self.log(f"Lỗi khi quét cổng: {e}")

        # Update combobox
        values = []
        for d in self.devices:
            values.append(f"{d['port']}  ({d['driver']})")

        current_selection = self.dev_combo.get()
        self.dev_combo["values"] = values

        if values:
            if current_selection in values:
                self.dev_combo.set(current_selection)
            else:
                self.dev_combo.current(0)
            self._update_selected_info()
        else:
            self.dev_combo.set("Không phát hiện cổng serial nào")
            self.lbl_driver.config(text="Không có", foreground="#666666")
            self.lbl_patch_status.config(text="Không có thiết bị", style="BadgeYellow.TLabel")
            self.lbl_dtr_status.config(text="Không có thiết bị", style="BadgeYellow.TLabel")
            self.btn_toggle_block.config(state=tk.DISABLED)
            self.btn_toggle_allow.config(state=tk.DISABLED)
            self.btn_patch.config(state=tk.DISABLED)
            self.btn_restore.config(state=tk.DISABLED)

    def _on_device_selected(self, event=None):
        self._update_selected_info()

    def _update_selected_info(self):
        idx = self.dev_combo.current()
        if idx < 0 or idx >= len(self.devices):
            return

        dev = self.devices[idx]
        driver = dev["driver"]
        self.lbl_driver.config(text=f"{driver} ({dev['port']})", foreground="#000000")

        # Check sysfs parameters
        param_file = f"/sys/module/{driver}/parameters/disable_dtr_rts"
        backup_file = f"/var/backups/uart_dtr_patch/{driver}.kver"

        if os.path.isfile(param_file):
            try:
                with open(param_file, "r") as f:
                    val = f.read().strip()
                self.lbl_patch_status.config(text="ĐÃ CÀI ĐẶT (Deep Patched)", style="BadgeGreen.TLabel")
                if val in ("Y", "1"):
                    self.lbl_dtr_status.config(text="ĐANG CHẶN RESET (An toàn cho Gimbal)", style="BadgeGreen.TLabel")
                else:
                    self.lbl_dtr_status.config(text="MẶC ĐỊNH UBUNTU (DTR/RTS hoạt động)", style="BadgeRed.TLabel")
                self.btn_toggle_block.config(state=tk.NORMAL)
                self.btn_toggle_allow.config(state=tk.NORMAL)
            except Exception as e:
                self.lbl_patch_status.config(text="Lỗi đọc tham số", style="BadgeRed.TLabel")
        else:
            self.lbl_patch_status.config(text="DRIVER GỐC (Chưa patch)", style="BadgeYellow.TLabel")
            self.lbl_dtr_status.config(text="MẶC ĐỊNH UBUNTU (Có thể gây Reset Gimbal)", style="BadgeRed.TLabel")
            self.btn_toggle_block.config(state=tk.DISABLED)
            self.btn_toggle_allow.config(state=tk.DISABLED)

        self.btn_patch.config(state=tk.NORMAL)
        if os.path.isfile(backup_file):
            self.btn_restore.config(state=tk.NORMAL)
        else:
            self.btn_restore.config(state=tk.NORMAL)

    def _schedule_auto_refresh(self):
        # Auto refresh ports every 3 seconds if not executing command
        if not self.is_operating:
            self.refresh_devices()
        self.root.after(3000, self._schedule_auto_refresh)

    def _get_current_driver(self) -> str:
        idx = self.dev_combo.current()
        if idx >= 0 and idx < len(self.devices):
            return self.devices[idx]["driver"]
        return "cp210x"

    # ==========================================================================
    # Asynchronous Core Execution using pkexec
    # ==========================================================================

    def _run_core_command(self, args: list, task_name: str, on_complete=None):
        if self.is_operating:
            return

        self.set_operating(True, f"Đang thực hiện: {task_name}...")
        self.log(f"\n--- [BẮT ĐẦU: {task_name}] ---")

        def worker():
            cmd = ["pkexec", CORE_SCRIPT] + args
            self.log(f"Lệnh: {' '.join(cmd)}")

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                for line in proc.stdout:
                    clean_line = line.rstrip()
                    # Strip ANSI color codes for log box
                    clean_line = self._strip_ansi(clean_line)
                    self.log(clean_line)

                proc.wait()
                rc = proc.returncode

                if rc == 0:
                    self.log(f"--- [THÀNH CÔNG: {task_name}] ---")
                    msg = f"{task_name} hoàn tất thành công!"
                elif rc == 126 or rc == 127:
                    self.log(f"--- [HỦY BỎ BỞI NGƯỜI DÙNG: {task_name}] ---")
                    msg = "Người dùng đã hủy xác thực mật khẩu."
                else:
                    self.log(f"--- [THẤT BẠI: {task_name} (Mã lỗi: {rc})] ---")
                    msg = f"{task_name} thất bại (Code: {rc}). Xem chi tiết trong log."

            except Exception as e:
                self.log(f"Lỗi thực thi: {e}")
                msg = f"Lỗi: {e}"

            def finish():
                self.set_operating(False, msg)
                self.refresh_devices()
                if on_complete:
                    on_complete()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _strip_ansi(self, text: str) -> str:
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    # ==========================================================================
    # Action Handlers
    # ==========================================================================

    def toggle_dtr(self, value: int):
        driver = self._get_current_driver()
        task = "Bật Chặn Reset (DTR/RTS OFF)" if value == 1 else "Tắt Chặn Reset (Mặc định)"
        self._run_core_command(["toggle", driver, str(value)], task)

    def patch_driver(self):
        driver = self._get_current_driver()
        confirm = messagebox.askyesno(
            "Xác nhận Cài Đặt Deep Patch",
            f"Bạn có muốn biên dịch và cài đặt Deep Patch cho driver '{driver}'?\n\n"
            "Thao tác này yêu cầu quyền Administrator (sẽ có cửa sổ hỏi mật khẩu Ubuntu).",
            parent=self.root
        )
        if not confirm:
            return

        self._run_core_command(["patch", driver, "-y"], f"Cài đặt Deep Patch ({driver})")

    def restore_driver(self):
        driver = self._get_current_driver()
        confirm = messagebox.askyesno(
            "Xác nhận Khôi Phục Driver Gốc",
            f"Bạn có muốn gỡ bỏ Deep Patch và khôi phục lại driver '{driver}' nguyên bản của Ubuntu?\n\n"
            "Lưu ý: Nếu driver đang bận, hãy rút cáp USB ra trước.",
            parent=self.root
        )
        if not confirm:
            return

        self._run_core_command(["restore", driver, "-y"], f"Khôi phục driver gốc ({driver})")


def main():
    if not os.path.isfile(CORE_SCRIPT):
        print(f"Lỗi: Không tìm thấy file core: {CORE_SCRIPT}")
        sys.exit(1)

    root = tk.Tk()
    app = UARTControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
