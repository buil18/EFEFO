# Thay đổi

## 1.1.0 — theo `SAP_FULL_27_8_v6.py` + hai công cụ theo dõi

### Logic mới từ v6 (đã kiểm chứng giống hệt v6 bằng 25 test đối chứng)
- Loại dòng FEFO có tổng số lượng < 100 (hàng lẻ / hết hàng), cấu hình bằng `[fefo] min_quantity`; 0 = tắt.
- Thứ tự phụ khi trùng % shelf life: số lượng **tăng dần**, rồi tên vị trí.
- Audit: lô SAP cách dòng FEFO gần nhất ≥ `lot_split_days` ngày không bị gán sang nhóm cũ hơn.

### Thêm
- `python -m efefo perf-report`: thay `bao_cao_hieu_nang_pad.py`. Tự tìm thư mục log theo site. Kết quả giống hệt script gốc.
- `python -m efefo fefo-history`: thay `kiem_tra_lich_su_fefo.py`. Tự tìm `audit/history` theo site. Kết quả giống hệt script gốc; riêng các lô trùng % được in theo thứ tự ổn định thay vì ngẫu nhiên.
- Mục cấu hình `[monitoring]` (chu kỳ chạy 30 phút, ngưỡng đứt 45 phút). Số ô hiển thị và ngưỡng tụt dữ liệu của `fefo-history` lấy từ `[fefo]` và `[audit]`, không còn viết cứng.
- Pipeline ghi phần **tổng kết lượt chạy** (`sap`/`report` + `THÀNH CÔNG`/`THẤT BẠI`/`BỎ QUA` + thời gian, và `Tất cả các bước đã hoàn tất`) để `perf-report` phân loại được lượt chạy. Dòng mở đầu lượt `Đã bật ghi log file` được ghi ở **mọi** lượt.
- `apps_script/Code.gs` và `apps_script/Index.html`: giữ nguyên văn bản đang chạy, kèm hướng dẫn triển khai `docs/APPS_SCRIPT.md`.
- `scripts/perf_report.bat`, `scripts/fefo_history.bat`.

## 1.0.0 — thay thế `SAP_FULL_27_8_v5.py`

Các khác biệt có chủ đích dưới đây vẫn áp dụng cho 1.1.0 so với v6.

### Giữ nguyên
- Toàn bộ quy tắc nghiệp vụ, thứ tự các bước, tên file, thư mục output, cột báo cáo, định dạng payload Apps Script, file trạng thái audit. Đã kiểm chứng bằng 25 test đối chứng với v5.
- Thông điệp log (tiếng Việt) giữ như cũ. Riêng lệnh gợi ý chạy lại đổi từ `python run_all.py --only sap --interactive` thành `python -m efefo run --site <site> --interactive`.

### Cấu trúc
- Một file 2.746 dòng được tách thành 36 module trong 6 nhóm (1.1: 38 module, thêm nhóm `tools`) (`sap`, `sources`, `domain`, `reports`, `audit`, `infra`).
- Toàn bộ giá trị riêng của site chuyển sang `sites/<site>.toml`. Thêm lệnh `check`, `new-site`, `sites`.
- Code không chứa comment. Giải thích nằm trong `docs/`.
- Việc gửi dữ liệu lên Apps Script bật/tắt bằng `[publish]`.

### Khác biệt có chủ đích
| # | v5 | 1.0 | Lý do |
|---|---|---|---|
| 1 | Một giá trị `/Date()/` không có số trong dữ liệu SAP làm **dừng cả lượt chạy** (`AttributeError`) | Giữ nguyên giá trị đó, lượt chạy tiếp tục | Sửa lỗi; có test `test_known_legacy_crash_on_empty_sap_date_is_fixed` |
| 2 | Bin bắt đầu bằng `HMPKG` bị xóa **mọi** chuỗi `HMPKG` trong tên | Chỉ bỏ tiền tố ở đầu tên | Quy tắc chung cho mọi site. Chỉ khác khi tên bin chứa `HMPKG` hai lần, điều không xảy ra với bin thật |
| 3 | Phiên đăng nhập lưu ở `.session/` cạnh script | Lưu ở `.session/<site>/` trong thư mục dự án | Mỗi site một phiên riêng. Chép file phiên cũ sang, hoặc đăng nhập lại 1 lần |
| 4 | Secret mặc định viết thẳng trong code | Đọc từ biến môi trường, hoặc `sites/hm.local.toml` (không lên git) | Bảo mật |
| 5 | Bản chốt đầu ngày được ghi lại từ DataFrame | Chép từ file vừa ghi (nếu ghi thành công) | Nhanh hơn; nội dung giống hệt |
| 6 | Ghi Excel bằng openpyxl | Ghi bằng xlsxwriter nếu đã cài (vẫn dùng openpyxl cho FEFO.xlsx) | Nhanh hơn; giá trị ô giống hệt |

### Phụ thuộc
- Giới hạn `pandas<3`. pandas 3 đổi cách xử lý giá trị thiếu khi chuyển sang chữ, và gặp lỗi nội bộ với một số dữ liệu hỏng.
- Thêm `xlsxwriter`.
