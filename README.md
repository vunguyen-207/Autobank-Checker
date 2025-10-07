## 🔧 Giới thiệu

Script này giúp bạn **kiểm tra liên tục các giao dịch ngân hàng** thông qua API của bất cứ bên hỗ trợ nào có trả output theo định dạng
```bash
{
  "status": true,
  "success": "Thành công",
  "data": [
    {
      "postingDate": "d/m/y h:m:s",
      "transactionDate": "d/m/y h:m:s",
      "accountNo": "number",
      "creditAmount": "price",
      "debitAmount": "number",
      "currency": "VND",
      "description": "CUSTOMER vndev CODE. TU: ACCOUNT HOLDER",
      "addDescription": "vndev CODE ",
      "availableBalance": "NUMBER",
      "beneficiaryAccount": "",
      "refNo": "CODE",
      "benAccountName": "MONEY TAKER",
      "bankName": "BANK NAME",
      "benAccountNo": "number",
      "dueDate": "",
      "docId": "",
      "transactionType": "TYPE",
      "pos": "",
      "tracingType": ""
    }
  ]
```
Khi phát hiện giao dịch hợp lệ (chứa nội dung chuyển khoản “VNDEV <CODE>” trong mô tả và số tiền khớp `expected.json`) > print **“Đã thanh toán”**.
Mọi trường hợp khác (thiếu code, sai số tiền, lỗi API, v.v.) sẽ được **in debug** để dễ theo dõi.

---

## ⚙️ Cách cài đặt

### 1️⃣ Yêu cầu

* Python **3.8+**
* Thư viện cần thiết:

  ```bash
  pip install aiohttp
  ```

### 2️⃣ Clone hoặc tải script

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

---

## 🚀 Cách chạy

### ▶️ Chạy một lần (fetch API 1 lần rồi thoát)

```bash
python check_autobuy.py --loop 0
```

### 🔁 Chạy liên tục (mặc định 10 giây/lần)

```bash
python check_autobuy.py
```

* Mặc định kiểm tra mỗi **10 giây**.
* Các giao dịch đã in “Đã thanh toán” sẽ **không bị print lại** (do chống trùng `refNo`).

---

## 📁 Cấu trúc file `expected.json`

Đây là nơi bạn khai báo mã CODE và số tiền cần đối chiếu:

```json
{
  "ABC123": 30000,
  "XYZ9QW": 170000
}
```

> ⚠️ CODE phải là 6 ký tự (chữ và số), trùng với nội dung “VNDEV <CODE>” trong mô tả giao dịch.

---

## 🧠 Tham số dòng lệnh

| Tham số      | Mặc định                      | Mô tả                                                           |
| ------------ | ----------------------------- | --------------------------------------------------------------- |
| `--url`      | API mặc định trong file       | Đường dẫn API bạn muốn kiểm tra                                 |
| `--expected` | `expected.json`               | Đường dẫn đến file chứa mapping CODE > amount                   |
| `--loop`     | `10`                          | Số giây giữa mỗi lần check (0 = chỉ chạy một lần)               |
| `--dedup`    | `2000`                        | Số lượng `refNo` được log để tránh in trùng “Đã thanh toán”     |

Ví dụ:

```bash
python check_autobuy.py --url "https://api.web2m.com/historyapimb/..." --expected "./expected.json" --loop 5
```

---

## 🧩 Cách hoạt động

1. Gọi API > lấy danh sách giao dịch.
2. Bỏ qua giao dịch rút tiền (`debit > 0`).
3. Tìm nội dung chuyển khoản chứa `"VNDEV <CODE>"`.
4. Nếu `CODE` tồn tại trong `expected.json` và `creditAmount` khớp > print **“Đã thanh toán”**.
5. Nếu sai khác > debug.

---

## 🧱 Ví dụ output

```text
[AutoBuy] Đã track 4 giao dịch.
[AutoBuy] Thiếu token (Thực tế là nội dung chuyển khoản) 'VNDEV': refNo=MB12345, desc='NAP TIEN MOMO'
Đã thanh toán
[AutoBuy] Giao dịch lệch tiền: refNo=MB67890, code=ABC123, expected=30000, actual=25000
```

---

## 🛑 Dừng script

Ấn **Ctrl + C** để thoát an toàn. Script có xử lý `SIGINT`/`SIGTERM` cho bạn.

---

## 📜 Giấy phép

MIT License © 2025 — Bạn được phép tự do chỉnh sửa, tái sử dụng.
