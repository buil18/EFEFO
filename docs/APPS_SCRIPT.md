# Google Apps Script và giao diện tablet

Thư mục `apps_script/` chứa **nguyên văn** hai file đang chạy:

| File | Bản gốc | Vai trò |
|---|---|---|
| `Code.gs` | `Code_v3.gs` | Web App: nhận dữ liệu từ pipeline (`doPost`), trả dữ liệu cho tablet, ghi FLD_Report/Audit_Log/History_Log, gửi Zalo, báo cáo nhập kho theo ca |
| `Index.html` | `Index_v12.html` | Giao diện E-FEFO trên tablet (nhúng Google Sites) |

Theo yêu cầu, hai file này giữ nguyên, không sửa nội dung (kể cả comment). Quy tắc "không comment" chỉ áp dụng cho mã Python.

## Triển khai

1. Mở Google Sheet E-FEFO của site, vào **Extensions → Apps Script**.
2. Tạo hai file:
   - `Code.gs`: dán nội dung `apps_script/Code.gs`.
   - `Index` (loại HTML): dán `apps_script/Index.html`.

   Tên phải là `Index`, vì `doGet()` gọi `createHtmlOutputFromFile('Index')`.
3. Vào **Project Settings**:
   - Time zone = `(GMT+07:00) Asia/Ho_Chi_Minh`.
   - Script Properties:
     - `ZALO_CHAT_ID`;
     - `ZALO_WEBHOOK_URL`, hoặc cặp `ZALO_API_BASE` + `ZALO_BOT_TOKEN`.
4. Chạy hàm `setupShiftTriggers` một lần để tạo 3 trigger báo cáo theo ca (6h05, 14h05, 0h05).
5. **Deploy → New deployment → Web app**:
   - Execute as: Me.
   - Access: Anyone.
6. Copy URL `/exec` của Web App vào biến môi trường `GOOGLE_APPS_SCRIPT_URL` trên máy chạy pipeline, hoặc vào `fefo_script_url` trong `sites/<site>.local.toml`.
7. Nhúng URL Web App vào Google Sites.

Kiểm tra nhanh trong editor:
- `testGhiDuLieuTrucTiep`: ghi tab FEFO.
- `testGhiAuditLogTrucTiep`: ghi Audit_Log và gửi Zalo.
- `testZaloKetNoi`: chỉ thử kết nối Zalo.

## Các giá trị phải khớp với cấu hình Python

Apps Script và HTML không đọc được `sites/<site>.toml`. Khi đổi các giá trị dưới đây ở một phía, phải sửa phía còn lại:

| Apps Script / HTML | Python (`sites/<site>.toml`) | Giá trị HM | Nếu lệch |
|---|---|---|---|
| `Code.gs` → `validSecrets` | biến `GOOGLE_APPS_SCRIPT_SECRET` hoặc `[publish] secret` | (giá trị bí mật, không ghi trong tài liệu) | Apps Script từ chối dữ liệu |
| `Code.gs` → `FIXED_MAX_BATCHES` | `[fefo] display_max_slots` | 6 | Audit báo nhầm lô "ẩn" |
| `Code.gs` → `EXCLUDE_BIN_PREFIXES` | `[location] display_exclude_prefixes` | K, H | Audit báo nhầm Hidden-bin |
| `Code.gs` → `EXCLUDE_BIN_KEYWORDS` | `[location] display_exclude_keywords` | LOOSE | Như trên |
| `Index.html` → `HIDDEN_LOCATIONS` | `[location] display_exclude_keywords` | LOOSE | Tablet hiện vị trí lẽ ra phải ẩn |
| `Index.html` → `MAX_SLOTS_DEFAULT`, `MIN_SLOTS` | `[fefo] display_max_slots` | 6 | Tablet hiện số ô khác với audit |

Các giá trị chỉ có trong Apps Script và HTML, cần sửa khi nhân rộng sang site khác:
- **`Code.gs`:**
  - `HISTORY_SHEET_ID` (file Sheet History_Log);
  - `SHIFT_TZ` và giờ các ca;
  - nghiệp vụ `"Nhập kho WO"`.
- **`Index.html`:**
  - `DEVICE_NAMES` (tên tablet);
  - `ITEM_NOTES` (lưu ý đầu trang);
  - dòng hướng dẫn kênh bán (`guidanceBox`);
  - `LIMIT_SLOTS` (mã bán chậm).

## Luồng dữ liệu

```
pipeline Python ──POST {secret, header, rows}──────────► doPost → tab FEFO (ghi đè, J1 = giờ server)
                ──POST {secret, type:"audit", rows}─────► doPost → tab Audit_Log + Zalo
                ──POST {secret, header, rows} (Capacity)► Web App Capacity (project riêng, không nằm trong repo)
tablet Index.html ──google.script.run──► getFefoData / getFefoUpdateTime (5 phút/lần, chỉ đọc J1)
                  ──google.script.run──► submitFldReport → FLD_Report + Zalo lần đầu
```

`Code.gs` còn nhánh `type: "history"` (ghi History_Log vào file Sheet khác). Pipeline Python hiện **không** gửi loại dữ liệu này, nên nhánh đó chỉ hoạt động khi có nguồn khác gửi tới.

## Thứ tự hiển thị trên tablet

- `getFefoData` sắp lại các lô của từng mã chỉ theo `% shelf life`. Phép sắp này giữ nguyên thứ tự gốc khi các lô bằng nhau, nên các lô cùng % vẫn giữ thứ tự Python đã gửi lên.
- Từ v6, thứ tự Python đã gửi là: dòng SAP trước dòng kiểm kho, rồi số lượng **tăng dần**, rồi tên vị trí.
- Kết quả: bin còn ít hàng luôn hiện trước để dọn trống bin, đúng mục tiêu của v6.
