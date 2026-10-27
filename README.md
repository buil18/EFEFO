# E-FEFO

Hệ thống FEFO cho kho, gồm 3 phần:

1. **Pipeline Python** (`efefo/`)
   - Lấy tồn kho SAP S/4HANA EWM qua OData.
   - Làm giàu dữ liệu bằng master data và kiểm kho thực tế.
   - Xuất báo cáo tồn kho, báo cáo đối chiếu, bảng FEFO.
   - Theo dõi audit Blocked / Hidden-bin giữa các lần chạy.
2. **Google Apps Script + giao diện tablet** (`apps_script/`)
   - Nhận bảng FEFO từ pipeline.
   - Hiển thị E-FEFO trên tablet xe nâng.
   - Nhận báo lỗi vị trí và gửi Zalo.
3. **Công cụ theo dõi**
   - Báo cáo hiệu năng các lượt chạy tự động (`perf-report`).
   - Tra lịch sử hiện/ẩn của một vị trí trên E-FEFO (`fefo-history`).

Mỗi site (kho) là **một file cấu hình** `sites/<mã>.toml`. Code dùng chung, không chứa giá trị riêng của site.

> Bản 1.1 tương ứng `SAP_FULL_27_8_v6.py`, `bao_cao_hieu_nang_pad.py`, `kiem_tra_lich_su_fefo.py`. Đã kiểm chứng kết quả **giống hệt** các script gốc bằng bộ test đối chứng (xem [docs/TESTING.md](docs/TESTING.md)).

## Bắt đầu nhanh (Windows + VS Code)

```bat
git clone <repo> efefo
cd efefo
scripts\setup.bat
.venv\Scripts\python -m efefo check --site hm
scripts\run_hm.bat --interactive
```

- Lần đầu chạy `--interactive` để đăng nhập SAP (MFA).
- Các lần sau chạy `scripts\run_hm.bat` từ Task Scheduler hoặc Power Automate Desktop.
- Chuyển đổi từ script cũ: xem [docs/OPERATIONS.md](docs/OPERATIONS.md#chuyển-từ-sap_full_27_8_v6py).

## Lệnh

| Lệnh | Tác dụng |
|---|---|
| `python -m efefo run --site hm` | Chạy toàn bộ pipeline (lập lịch tự động) |
| `python -m efefo run --site hm --interactive` | Như trên, cho phép mở Edge để đăng nhập/MFA |
| `python -m efefo check --site hm` | Kiểm tra cấu hình, file đầu vào, cột bắt buộc |
| `python -m efefo perf-report --site hm [--tu 2026-10-01 --den 2026-10-24]` | Báo cáo hiệu năng các lượt chạy → `Bao_cao_hieu_nang_PAD.xlsx` |
| `python -m efefo fefo-history --site hm --mat 10079432 --loc E23 [--date 2026-10-22] [--chi-tiet]` | Lịch sử hiện/ẩn của vị trí trên E-FEFO |
| `python -m efefo new-site dn` | Tạo `sites/dn.toml` từ mẫu |
| `python -m efefo sites` | Liệt kê các site |

Mỗi lệnh có file `.bat` tương ứng trong `scripts/`.

## Cấu trúc dự án

```
efefo/
├── efefo/                  Pipeline Python (không comment, tài liệu ở docs/)
│   ├── cli.py              Lệnh dòng lệnh
│   ├── config.py           Đọc + kiểm tra cấu hình site (TOML)
│   ├── context.py          Đường dẫn, biến môi trường cho một lượt chạy
│   ├── runner.py           Trình tự các bước, ghi tổng kết lượt chạy
│   ├── checks.py           Lệnh check
│   ├── sap/                Đăng nhập (Playwright/Edge), tải OData, làm sạch ngày giờ SAP
│   ├── sources/            Google Sheet kiểm kho, Shelflife.xlsx, Capacity.xlsx, danh sách mã bổ sung
│   ├── domain/             Nghiệp vụ: vị trí, shelf life, capacity, mã bổ sung, FEFO, đối chiếu
│   ├── reports/            Xuất Excel và gửi Google Apps Script
│   ├── audit/              Theo dõi Blocked / Hidden-bin giữa các lần chạy
│   ├── tools/              perf_report.py, fefo_history.py
│   └── infra/              Log, khóa chạy trùng, ghi file có thử lại, HTTP
├── apps_script/            Code.gs + Index.html (giữ nguyên bản đang chạy)
├── sites/                  hm.toml, _template.toml, *.local.toml (secret, không lên git)
├── scripts/                setup, run_site, run_hm, perf_report, fefo_history, register_task
├── tests/                  unit/, parity/ (đối chứng script gốc), stress/
└── docs/                   Tài liệu
```

## Tài liệu

| File | Nội dung |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Luồng dữ liệu, vai trò từng module, ánh xạ từ script gốc |
| [docs/BUSINESS_RULES.md](docs/BUSINESS_RULES.md) | Toàn bộ quy tắc nghiệp vụ đang áp dụng |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Từng khóa cấu hình site và biến môi trường |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Cài đặt, lập lịch, công cụ theo dõi, xử lý sự cố |
| [docs/APPS_SCRIPT.md](docs/APPS_SCRIPT.md) | Triển khai Apps Script + giao diện tablet, các điểm phải đồng bộ với Python |
| [docs/NEW_SITE.md](docs/NEW_SITE.md) | Quy trình nhân rộng sang site mới |
| [docs/TESTING.md](docs/TESTING.md) | Chiến lược test, QA test case, kết quả stress/hiệu năng |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Lịch sử thay đổi |
