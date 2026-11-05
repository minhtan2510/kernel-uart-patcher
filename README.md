# Kernel UART Patcher — Linux DTR/RTS Reset Shield (Deep Patch)

Bộ công cụ giải quyết triệt để vấn đề Ubuntu Kernel và Ứng dụng điều khiển chân DTR/RTS khi kết nối UART, làm kéo chân Reset của thiết bị (Gimbal, STM32, ESP32, Arduino) xuống mức LOW.

---

## 1. Cấu Trúc Thư Mục (Project Structure)

Project được cấu trúc tinh gọn với **1 file chạy duy nhất ở thư mục gốc**:

```text
LinuxUART/
├── run.sh                       # File chạy duy nhất ở thư mục gốc (Khởi động GUI)
├── README.md                    # Tài liệu hướng dẫn
├── .gitignore
└── src/
    ├── core/                    # Core Engine (Driver patcher & Kernel module script)
    │   ├── patch_driver.py      # Bộ tạo mã Deep Patch 5 tầng cho driver C
    │   └── uart_kernel_patch.sh # Script quản lý biên dịch, cài đặt, an toàn module
    └── gui/                     # Giao diện đồ họa Modern Minimalist
        └── gui.py               # Ứng dụng GUI siêu nhỏ gọn (Ultra-Compact Widget)
```

---

## 2. Hướng Dẫn Khởi Chạy Nhanh (Quick Start)

Ở thư mục gốc, chỉ cần chạy một lệnh duy nhất:

```bash
cd ~/Desktop/Script/LinuxUART
./run.sh
```

**Tính năng nổi bật của GUI:**
- **Ultra-Compact Widget**: Cửa sổ nhỏ gọn (chỉ 350x275 px), tự động căn giữa màn hình.
- **Modern Minimalist Style**: Dark mode chuẩn Tailwind Zinc/Slate kết hợp font Inter & JetBrains Mono.
- **Tiếng Anh 100%**: Nhãn, thông báo trạng thái, popup xác nhận và log chuẩn quốc tế.
- **One-Touch Shield**: Chuyển đổi tức thời giữa trạng thái **Shield Active** (khóa DTR/RTS High, chặn reset) và **Shield Inactive**.
- **Driver Operations**: Tích hợp các thao tác `Patch Driver` và `Restore Stock` với xác thực đồ họa `pkexec`.
- **Auto-Expanding Log**: Ngăn nhật ký tự động mở khi đang thao tác và có thể thu gọn tùy ý.

---

## 3. Kiến Trúc "Deep Patch" (5 Tầng Phòng Ngự)

Bản **Deep Patch** can thiệp toàn diện vào cả 5 tầng xử lý của driver (`cp210x`, `ch341`, `ftdi_sio`):

| Tầng can thiệp | Vị trí trong Driver | Tác động |
|---|---|---|
| **1. Module Parameter** | `disable_dtr_rts` | Tham số kernel module cho phép bật/tắt live qua `/sys/module/<mod>/parameters/disable_dtr_rts` mà **không cần biên dịch lại hay reload module**. |
| **2. Port Open** | `cp210x_open()` | Ngay sau khi kích hoạt UART, driver gửi ngay lệnh phần cứng ép DTR và RTS lên mức **HIGH (3.3V - Inactive)**. |
| **3. IOCTL Interceptor** | `cp210x_tiocmset_port()` | Chặn và bóc tách bit `TIOCM_DTR` và `TIOCM_RTS` khỏi tham số `set`. Dù App hoặc thư viện serial có gọi `ioctl` đòi kéo DTR xuống LOW thì driver vẫn **từ chối và ép giữ HIGH**. |
| **4. Kernel Callback** | `cp210x_dtr_rts()` | Bỏ qua tham số `on`, luôn ép chân DTR/RTS về mức Inactive. |
| **5. Flow Control** | `cp210x_set_flow_control()` | Ép `port_priv->dtr = false`, ghi cờ `CP210X_SERIAL_DTR_INACTIVE` vào thanh ghi phần cứng. |

---

## 4. Hướng Dẫn Sử Dụng Bằng Dòng Lệnh (CLI)

Nếu không dùng giao diện, bạn có thể gọi trực tiếp script trong `src/core/`:

### Bước 1: Áp dụng Deep Patch vào driver thiết bị (ví dụ CP2102N)
```bash
cd ~/Desktop/Script/LinuxUART
sudo ./src/core/uart_kernel_patch.sh patch cp210x
# (hoặc cắm USB vào rồi chạy: sudo ./src/core/uart_kernel_patch.sh patch /dev/ttyUSB0)
```

### Bước 2: Bật/Tắt Live (Không cần reload driver hay cắm lại thiết bị)
- **Tạm thời khôi phục hành vi mặc định của Ubuntu Kernel:**
  ```bash
  sudo ./src/core/uart_kernel_patch.sh toggle cp210x 0
  ```
- **Kích hoạt lại chế độ chặn Reset DTR/RTS:**
  ```bash
  sudo ./src/core/uart_kernel_patch.sh toggle cp210x 1
  ```

### Bước 3: Khôi phục hoàn toàn driver gốc ban đầu của Ubuntu
```bash
sudo ./src/core/uart_kernel_patch.sh restore cp210x
```
