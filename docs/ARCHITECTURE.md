# Kiến trúc

## Luồng một lượt chạy

```
python -m efefo run --site hm
        │
        ▼
config.load_site("hm")            sites/hm.toml + sites/hm.local.toml
context.build_context()           thư mục, biến môi trường, URL, danh sách mã bổ sung
runner.run()
 ├─ infra.logging_setup           logs/sap_inventory.log (xoay theo ngày), dòng "Đã bật ghi log file" mở đầu lượt
 ├─ context.validate_input_files  thiếu Shelflife/Capacity → dừng
 ├─ infra.run_lock                .sap_inventory.lock (hết hạn sau 3 giờ)
 ├─ sap.client.fetch_all_records  Edge + phiên lưu sẵn → OData phân trang, tự phục hồi
 ├─ ghi sap_response_full.json
 └─ runner.process()
     ├─ sources.stock_count       Google Sheet kiểm kho (CSV) + danh sách vị trí Blocked
     ├─ runner.transform()
     │   ├─ sap.cleaning                  /Date(ms)/ → ngày, PT#H#M#S → giờ
     │   ├─ domain.supplement             thêm mã ngoài SAP + lọc theo lịch sử vị trí
     │   ├─ sources.master_data           Shelflife.xlsx, sheet Unit của Capacity.xlsx
     │   ├─ domain.supplement             số lượng dòng kiểm kho, loại dòng số lượng 0
     │   ├─ domain.shelf_life             hạn dùng, % shelf life, phân loại tồn, pallet
     │   ├─ domain.capacity               vị trí chuẩn hóa, nhóm kho, occupancy
     │   └─ domain.supplement             loại dòng kiểm kho thiếu master data
     ├─ domain.fefo.build_fefo_summary    tính MỘT lần, dùng lại cho mọi đầu ra
     └─ runner.publish()
         ├─ reports.reconciliation        Inventory_Reconciliation_Report.xlsx
         ├─ reports.inventory             Inventory_Report_Full.xlsx + Daily_Reports/
         ├─ reports.fefo_workbook         FEFO.xlsx
         ├─ reports.google_sheet          POST bảng FEFO (nếu bật)
         ├─ reports.empty_locations       POST vị trí trống (nếu bật)
         └─ audit.step.run_audit_step     audit/ + POST type=audit (nếu bật)
 └─ runner.StepLog                Tổng kết lượt chạy: "  sap  THÀNH CÔNG  85.2s", "Tất cả các bước đã hoàn tất"
```

Công cụ theo dõi (chỉ ĐỌC dữ liệu do pipeline tạo ra):

```
python -m efefo perf-report   logs/sap_inventory.log*      → tools.perf_report  → Bao_cao_hieu_nang_PAD.xlsx
python -m efefo fefo-history  audit/history/*.json.gz      → tools.fefo_history → báo cáo văn bản
```

`perf-report` dựa vào 3 loại dòng log do pipeline ghi: dòng mở đầu lượt, dòng `Tải OData xong`, và các dòng tổng kết của `runner.StepLog`. Khi sửa các thông điệp này phải sửa cả biểu thức nhận dạng trong `tools/perf_report.py`.

## Nguyên tắc phân lớp

| Lớp | Được làm | Không được làm |
|---|---|---|
| `domain/` | Tính toán trên DataFrame, nhận tham số cấu hình | Đọc biến môi trường, gọi mạng |
| `sources/` | Đọc file/URL đầu vào, chuẩn hóa cột | Quyết định nghiệp vụ |
| `reports/` | Ghi file, gửi HTTP | Thay đổi dữ liệu nghiệp vụ |
| `audit/` | So sánh trạng thái giữa các lần chạy | Sửa bảng FEFO |
| `runner.py` | Sắp thứ tự các bước, bật/tắt theo cấu hình | Chứa logic tính toán |
| `config.py`, `context.py` | Nơi DUY NHẤT đọc cấu hình site và biến môi trường | |

Mọi phụ thuộc bên ngoài (tải SAP, phiên HTTP) đi qua `runner.Services`, nên test có thể thay bằng bản giả mà không cần mạng.

## Ánh xạ từ `SAP_FULL_27_8_v5.py`

| v5 | Bản mới |
|---|---|
| `get_config`, `_resolve_*`, `_locate_input_file`, `validate_input_files` | `context.py` |
| Hằng số rải rác (URL, tiền tố bin, ngưỡng, vị trí loại trừ…) | `sites/hm.toml` |
| `_is_unattended`, `_get_credentials`, `_session_is_valid`, `_interactive_login`, `LOGIN_*` | `sap/auth.py` |
| `fetch_all_records`, `_relaunch_headed` | `sap/client.py` |
| `_fetch_odata_pages`, `_download_with_recovery`, `_log_download_diagnostics` | `sap/odata.py` |
| `clean_sap_date`, `clean_sap_time`, `clean_dataframe` | `sap/cleaning.py` |
| `fetch_google_sheet_df`, `get_blocked_locations`, `_log_location_mismatches` | `sources/stock_count.py` |
| `merge_shelf_life`, `merge_unit_capacity` | `sources/master_data.py` |
| `parse_manual_only_materials` | `sources/manual_materials.py` |
| `normalize_location_for_matching`, `normalize_sap_bin`, `get_warehouse_group`, `_audit_is_excluded_location` | `domain/location.py` |
| `get_stock_health`, `compute_shelf_life_metrics` | `domain/shelf_life.py` |
| `map_capacity_logic`, `compute_occupancy` | `domain/capacity.py` |
| `_detect_prd_date_order`, `_parse_prd_date_robust` | `domain/prd_date.py` |
| `_prepare_manual_frame` … `drop_manual_rows_without_shelf_life` | `domain/supplement.py` |
| `load/save_sap_location_history`, `filter_manual_rows_by_history` | `domain/location_history.py` |
| `reconcile_with_google_sheet` | `domain/reconciliation.py` + `reports/reconciliation.py` |
| `_gan_nhom_lo`, `build_fefo_summary`, `_flag/_mark_manual_*` | `domain/fefo.py` |
| `export_final_excel` | `reports/inventory.py` |
| `export_to_fefo` | `reports/fefo_workbook.py` |
| `export_to_google_sheet` | `reports/google_sheet.py` |
| `export_empty_locations_to_google_sheet` | `reports/empty_locations.py` |
| `_audit_*`, `run_audit_step` | `audit/snapshot.py`, `audit/detection.py`, `audit/storage.py`, `audit/step.py` |
| `setup_file_logging`, `acquire/release_run_lock`, `_to_excel_with_retry`, `_requests_session_with_retry` | `infra/` |
| `main` | `runner.py` + `cli.py` |
| `bao_cao_hieu_nang_pad.py` | `tools/perf_report.py` (lệnh `perf-report`) |
| `kiem_tra_lich_su_fefo.py` | `tools/fefo_history.py` (lệnh `fefo-history`) |

## Phạm vi

`apps_script/Code.gs` và `apps_script/Index.html` là bản đang chạy, giữ nguyên văn (xem [APPS_SCRIPT.md](APPS_SCRIPT.md)). Pipeline gửi dữ liệu lên Apps Script, bật/tắt bằng 3 cờ trong `[publish]` (xem [CONFIGURATION.md](CONFIGURATION.md#publish)). Tắt cả 3 cờ thì pipeline chỉ tạo file Excel và audit cục bộ.
