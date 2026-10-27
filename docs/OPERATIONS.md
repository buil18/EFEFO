# Vận hành

## Cài đặt

Yêu cầu:
- Windows có Microsoft Edge.
- Python 3.11 trở lên (máy hiện tại dùng 3.12).

```bat
cd efefo
scripts\setup.bat
```

`setup.bat` tạo `.venv` và cài các gói trong `requirements-dev.txt`. Playwright dùng Edge đã cài sẵn trên máy (`browser_channel = "msedge"`), không cần chạy `playwright install`.

pandas được giới hạn `<3`. Bộ test đã chạy với pandas 2.2. pandas 3 đổi cách xử lý giá trị thiếu khi chuyển sang chữ, nên chưa dùng.

## Chuyển từ `SAP_FULL_27_8_v6.py`

1. **Thư mục output giữ nguyên.** Bản mới đọc và ghi đúng `%OneDrive%\HM Site Log Pillar - Documents\General\28. Inventory_SAP`, cùng tên file và thư mục con. Lịch sử vị trí, trạng thái audit và `audit\history` hiện có được dùng tiếp, không mất mốc so sánh.
2. **Phiên đăng nhập.** Script cũ lưu phiên ở `.session\` cạnh file script. Bản mới lưu ở `efefo\.session\hm\`. Chọn một trong hai cách:
   - chép `...\All in one\.session\.sap_session.json` sang `efefo\.session\hm\.sap_session.json`;
   - hoặc chạy `scripts\run_hm.bat --interactive` một lần để đăng nhập lại.
3. **Secret.** `sites\hm.local.toml` chứa secret cũ, nên hành vi giống script cũ. Nên chuyển secret sang biến môi trường `GOOGLE_APPS_SCRIPT_SECRET` rồi xóa dòng `secret` trong file.
4. **Lập lịch.** Trong Power Automate Desktop hoặc Task Scheduler, đổi lệnh đang chạy `run_sap.bat` / `SAP_FULL_27_8_v6.py` thành `efefo\scripts\run_hm.bat`. Nếu dùng Task Scheduler, có thể chạy:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Site hm -EveryMinutes 30
   ```
5. **Công cụ.** `bao_cao_hieu_nang_pad.py` và `kiem_tra_lich_su_fefo.py` được thay bằng `scripts\perf_report.bat hm` và `scripts\fefo_history.bat hm ...`, xem mục [Công cụ theo dõi](#công-cụ-theo-dõi). Hai lệnh mới tự tìm thư mục `logs` và `audit\history` theo site, nên không cần nhập đường dẫn.
6. **Apps Script.** Không phải làm gì: `apps_script/` là bản đang chạy.
7. **Chạy song song 1–2 ngày (khuyến nghị).** Để script cũ tiếp tục chạy như hiện nay. Chạy bản mới với:
   - `SAP_OUTPUT_DIR` trỏ sang thư mục thử, có file đầu vào chép từ `Data_Input`;
   - 3 cờ `[publish]` đặt `false` trong `hm.local.toml`.

   So sánh file Excel hai bên rồi mới chuyển hẳn.

## Chạy

| Mục đích | Lệnh |
|---|---|
| Chạy tự động | `scripts\run_hm.bat` |
| Đăng nhập lại/MFA | `scripts\run_hm.bat --interactive` |
| Kiểm tra trước khi chạy | `.venv\Scripts\python -m efefo check --site hm` |
| Thử nhanh 10 trang | `set SAP_TEST_MODE=1` rồi chạy |

Mã thoát:
- `0`: thành công.
- `1`: lỗi hoặc bỏ qua lượt (đang có lượt khác chạy, SAP trả 0 bản ghi).
- `2`: cấu hình sai.

## Công cụ theo dõi

### Báo cáo hiệu năng chạy tự động

```bat
scripts\perf_report.bat hm
scripts\perf_report.bat hm --tu 2026-10-01 --den 2026-10-24
scripts\perf_report.bat hm --chu-ky 30 --nguong-dut 45 --out C:\temp\hieu_nang.xlsx
```

- Đọc toàn bộ `logs\sap_inventory.log*` của site.
- Kết quả ghi ra `Bao_cao_hieu_nang_PAD.xlsx` trong thư mục output của site.
- File có 9 sheet: tỷ lệ hoàn tất, khoảng đứt dữ liệu, thời lượng, lượt lỗi, chất lượng số dòng SAP…
- Quy tắc tính: [BUSINESS_RULES.md §13](BUSINESS_RULES.md#13-báo-cáo-hiệu-năng-perf-report).

### Lịch sử hiện/ẩn của vị trí trên E-FEFO

```bat
scripts\fefo_history.bat hm --mat 10079432 --loc E23
scripts\fefo_history.bat hm --mat 10079432 --loc E23,E54 --date 2026-10-22
scripts\fefo_history.bat hm --mat 10079432 --loc E23 --date 2026-10-22 --chi-tiet
scripts\fefo_history.bat hm --mat 10079432 --loc E23 --from "2026-10-21 08:00" --to "2026-10-21 18:00"
scripts\fefo_history.bat hm --mat 10079432 --loc E23 --date 2026-10-21 --all --out ketqua.txt
```

- Công cụ chỉ đọc `audit\history` (giữ 7 ngày), không sửa gì.
- Kết quả cho biết vị trí hiện hay ẩn trong từng khoảng thời gian.
- Khi trạng thái đổi, công cụ chỉ ra lô nào chen lên trước hoặc lô nào đã mất.
- Kèm các cảnh báo về chất lượng dữ liệu.

## Vị trí file (output của site)

| Đường dẫn | Nội dung |
|---|---|
| `Data_Input\Shelflife.xlsx`, `Capacity.xlsx`, `SAP_MA_BO_SUNG.txt` | Đầu vào do người vận hành cập nhật |
| `FEFO.xlsx` | Mẫu và kết quả bảng FEFO |
| `Inventory_Report_Full.xlsx` | Tồn kho mới nhất (Power BI đọc file này) |
| `Daily_Reports\Inventory_Report_Full_<ngày>.xlsx` | Bản chốt đầu ngày |
| `Inventory_Reconciliation_Report.xlsx` | Đối chiếu SAP ↔ kiểm kho |
| `sap_response_full.json` | Dữ liệu OData thô của lượt gần nhất |
| `.sap_location_history.json` | Lịch sử vị trí SAP (7 ngày) |
| `audit\` | Trạng thái, nhật ký và lịch sử audit (snapshot dùng cho `fefo-history`) |
| `Bao_cao_hieu_nang_PAD.xlsx` | Kết quả `perf-report` |
| `logs\sap_inventory.log` | Log theo ngày |

## Xử lý sự cố

| Hiện tượng trong log | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Phát hiện file khóa còn hiệu lực` | Lượt trước chưa xong hoặc bị tắt ngang | Chờ, hoặc xóa `.sap_inventory.lock` nếu chắc chắn không có lượt nào đang chạy |
| `UnattendedCredentialError ... MFA` | Phiên hết hạn và cần MFA | `scripts\run_hm.bat --interactive` |
| `Tải OData chưa đủ ... Bỏ qua lượt chạy` | SAP hoặc mạng lỗi liên tục | Lượt sau tự chạy lại; dữ liệu FEFO lần trước vẫn giữ nguyên |
| `Thiếu file dữ liệu đầu vào bắt buộc` | Thiếu Shelflife/Capacity | Đặt file vào `Data_Input` |
| `File ... đang bị khóa` | Ai đó đang mở file Excel | Đóng file; chương trình tự thử lại 3 lần |
| `Mã ... có trên Sheet ... chưa có trong SAP/whitelist` | Mã mới chỉ có ở kiểm kho | Thêm mã vào `SAP_MA_BO_SUNG.txt` nếu cần đưa lên FEFO |
| `Audit: số dòng SAP tụt` | Nghi tải thiếu dữ liệu | Tự bỏ qua 1 lượt; nếu kéo dài thì kiểm tra SAP |
