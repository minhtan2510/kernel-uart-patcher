# Linux UART DTR/RTS Disable Tool (Deep Patch)

Bộ công cụ giải quyết triệt để vấn đề Ubuntu Kernel và Ứng dụng điều khiển chân DTR/RTS khi kết nối UART, làm kéo chân Reset của thiết bị (Gimbal, STM32, ESP32, Arduino) xuống mức LOW.

---

## 1. Tại Sao Can Thiệp Trước Đó "Chưa Đủ Sâu"?

Trong lần thử nghiệm đầu tiên, việc chỉ đặt `.dtr_rts = NULL` trong driver **không ngăn được việc Gimbal bị Reset** vì 3 lý do kỹ thuật sau:

1. **Ứng dụng userspace (PySerial, Gimbal GUI, QSerialPort) chủ động kéo DTR**:
   Khi app kết nối, thư viện serial của app gửi lệnh `ioctl(TIOCMSET)` hoặc `ioctl(TIOCMBIS)` yêu cầu bật DTR. Lệnh này gọi thẳng vào hàm `.tiocmset` của driver (`cp210x_tiocmset_port`), gửi gói tin USB `CP210X_SET_MHS` ép chân DTR xuống mức **LOW (0V)**.
2. **Khởi tạo phần cứng UART (`cp210x_open`)**:
   Khi cổng được mở, driver gửi lệnh `CP210X_IFC_ENABLE` để kích hoạt khối UART trong IC CP2102N. Nếu không chủ động gán trạng thái HIGH ngay lập tức, IC sẽ dùng cấu hình mặc định (kéo DTR xuống).
3. **Cấu hình Flow Control (`set_termios`)**:
   Mỗi khi thay đổi baudrate hoặc flow control, hàm `cp210x_set_flow_control` ghi thanh ghi `CP210X_SET_FLOW` có thể kích hoạt `CP210X_SERIAL_DTR_ACTIVE`.

---

## 2. Giải Pháp "Can Thiệp Sâu" (Deep Patch — 5 Tầng Phòng Ngự)

Bản **Deep Patch** can thiệp toàn diện vào cả 5 tầng xử lý của driver (`cp210x`, `ch341`, `ftdi_sio`):

| Tầng can thiệp | Vị trí trong Driver | Tác động |
|---|---|---|
| **1. Module Parameter** | `disable_dtr_rts` | Tham số kernel module cho phép bật/tắt live qua `/sys/module/<mod>/parameters/disable_dtr_rts` mà **không cần biên dịch lại hay reload module**. |
| **2. Port Open** | `cp210x_open()` | Ngay sau khi kích hoạt UART, driver gửi ngay lệnh phần cứng ép DTR và RTS lên mức **HIGH (3.3V - Inactive)**. |
| **3. IOCTL Interceptor** | `cp210x_tiocmset_port()` | Chặn và bóc tách bit `TIOCM_DTR` và `TIOCM_RTS` khỏi tham số `set`. Dù App hoặc thư viện serial có gọi `ioctl` đòi kéo DTR xuống LOW thì driver vẫn **từ chối và ép giữ HIGH**. |
| **4. Kernel Callback** | `cp210x_dtr_rts()` | Bỏ qua tham số `on`, luôn ép chân DTR/RTS về mức Inactive. |
| **5. Flow Control** | `cp210x_set_flow_control()` | Ép `port_priv->dtr = false`, ghi cờ `CP210X_SERIAL_DTR_INACTIVE` vào thanh ghi phần cứng. |

---

## 3. Hướng Dẫn Sử Dụng

### Bước 1: Áp dụng Deep Patch vào driver thiết bị (ví dụ CP2102N)
```bash
cd ~/Desktop/Script/LinuxUART
sudo ./uart_kernel_patch.sh patch cp210x
# (hoặc cắm USB vào rồi chạy: sudo ./uart_kernel_patch.sh patch /dev/ttyUSB0)
```
*Script tự động tải source driver tương ứng, áp dụng Deep Patch 5 tầng qua `patch_driver.py`, biên dịch và cài đặt module mới.*

### Bước 2: Cắm Gimbal vào và mở App kết nối
Gimbal sẽ **hoạt động bình thường**, chân Reset không bị kéo xuống LOW.

### Bước 3: Bật/Tắt Live (Không cần reload driver hay cắm lại thiết bị)
- **Muốn tạm thời khôi phục hành vi mặc định của Ubuntu Kernel:**
  ```bash
  sudo ./uart_kernel_patch.sh toggle cp210x 0
  ```
- **Muốn kích hoạt lại chế độ chặn Reset DTR/RTS:**
  ```bash
  sudo ./uart_kernel_patch.sh toggle cp210x 1
  ```

### Bước 4: Khôi phục hoàn toàn driver gốc ban đầu của Ubuntu
```bash
sudo ./uart_kernel_patch.sh restore cp210x
```
