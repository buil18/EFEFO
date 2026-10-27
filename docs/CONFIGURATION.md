# Cấu hình

## Thứ tự ưu tiên

1. Biến môi trường (máy chạy) — cao nhất
2. `sites/<site>.local.toml` — giá trị riêng máy/secret, **không đưa lên git**
3. `sites/<site>.toml` — cấu hình chung của site, đưa lên git

File TOML được kiểm tra chặt khi đọc. Thiếu khóa, sai tên khóa, sai kiểu dữ liệu hoặc ngưỡng không tăng dần thì chương trình dừng và in rõ khóa nào sai.

## Khóa trong `sites/<site>.toml`

### [site]
| Khóa | Ý nghĩa |
|---|---|
| `code` | Mã site (chữ thường), trùng tên file |
| `name` | Tên hiển thị |

### [sap]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `base_url` | `https://my420157.s4hana.cloud.sap` | Tenant S/4HANA Cloud |
| `odata_path` | `/sap/opu/odata/sap/ZUI_IM_BCTKTTT_O2/ZIM_BCTKTTT_MAIN` | Service OData tồn kho |
| `client` | `"100"` | sap-client |
| `browser_channel` | `msedge` | Trình duyệt Playwright dùng |
| `max_relogin_attempts` | 2 | Số lần đăng nhập lại khi hết phiên giữa chừng |
| `max_incomplete_retries` | 3 | Số lần tải tiếp khi lỗi mạng/SAP |
| `incomplete_retry_wait_seconds` | [5, 15, 30] | Thời gian chờ giữa các lần |
| `test_max_pages` | 10 | Số trang khi bật `SAP_TEST_MODE` |

### [paths]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `onedrive_subdir` | `HM Site Log Pillar - Documents/General/28. Inventory_SAP` | Thư mục output, tính từ `%OneDrive%` hoặc `%OneDriveCommercial%` |
| `fallback_dir` | `SAP_Inventory_Output` | Dùng khi máy không có OneDrive |
| `input_subdir` | `Data_Input` | Thư mục con chứa file đầu vào |

### [sources]
| Khóa | Ý nghĩa |
|---|---|
| `stock_count_csv_url` | Link CSV đã publish của Google Sheet kiểm kho |
| `shelf_life_file`, `capacity_file`, `manual_materials_file` | Tên file trong `Data_Input` |
| `fefo_file` | Tên file mẫu FEFO ở thư mục gốc output |

### [location]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `strip_prefixes` | HMPKG, PKG, HM | Tiền tố bin SAP cần bỏ, xét theo thứ tự |
| `warehouse_group_prefixes` | BL, F, G, E, D | Tiền tố xác định nhóm kho, xét theo thứ tự |
| `display_exclude_prefixes` | K, H | Vị trí không lên tablet (dùng cho audit) |
| `display_exclude_keywords` | LOOSE | Từ khóa vị trí không lên tablet |
| `empty_location_exclusions` | FDD1 … GDD3 | Vị trí không báo trống |
| `empty_location_capacity_column` | Capacity Bot | Cột sức chứa dùng cho báo cáo vị trí trống |

### [shelf_life]
Các ngưỡng phân loại tồn, phải tăng dần: `expired_max`, `near_expiry_below`, `traditional_below`, `emart_below`, `supermarket_max`. Xem [BUSINESS_RULES.md §6](BUSINESS_RULES.md#6-shelf-life-và-tình-trạng-tồn).

### [fefo]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `lot_split_days` | 7 | Ngưỡng tách lô theo ngày SX |
| `min_quantity` | 100 | Dòng FEFO có tổng số lượng nhỏ hơn mức này bị loại (hàng lẻ/hết hàng). 0 = tắt |
| `display_max_slots` | 6 | Số vị trí tối đa hiển thị trên tablet cho mỗi mã (audit hidden-bin) |
| `workbook_sheet` | Update Actual Count | Sheet ghi trong FEFO.xlsx |
| `workbook_start_row` | 4 | Dòng bắt đầu ghi |

### [manual]
`location_history_retention_days` (7): thời gian giữ lịch sử vị trí SAP.

### [audit]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `enabled` | true | Bật/tắt audit |
| `history_retention_days` | 7 | Giữ file `audit/history` |
| `qty_delta_threshold` | 100 | Mức giảm tối thiểu để báo Hidden-bin |
| `confirm_runs` | 2 | Số lượt liên tiếp để xác nhận |
| `pending_max_age_minutes` | 120 | Thời gian chờ xác nhận tối đa |
| `max_record_drop_ratio` | 0.05 | Tỷ lệ tụt số dòng SAP bị coi là tải thiếu |
| `max_consecutive_suspect` | 1 | Số lượt nghi tải thiếu được bỏ qua liên tiếp |
| `max_push_attempts` | 3 | Số lần thử gửi lại sự kiện |

### [publish]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `fefo_to_google_sheet` | true | Gửi bảng FEFO lên Apps Script |
| `empty_locations_to_google_sheet` | true | Gửi vị trí trống lên Apps Script Capacity |
| `audit_to_google_sheet` | true | Gửi sự kiện audit (Audit_Log/Zalo) |
| `fefo_script_url` | "" | URL Web App FEFO (nên đặt bằng biến môi trường) |
| `capacity_script_url` | URL hiện tại | URL Web App Capacity |
| `secret` | "" | Đặt trong `hm.local.toml` hoặc biến môi trường |

Tắt cả 3 cờ thì pipeline chỉ tạo file Excel và audit cục bộ, không gọi Apps Script.

### [run]
`lock_stale_hours` (3): khóa chạy trùng cũ hơn mức này thì tự xóa.

### [monitoring]
| Khóa | HM | Ý nghĩa |
|---|---|---|
| `expected_interval_minutes` | 30 | Chu kỳ chạy tự động mong đợi (mặc định `--chu-ky` của `perf-report`) |
| `gap_warning_minutes` | 45 | Hai lượt cách nhau quá mức này coi là đứt (mặc định `--nguong-dut`, và ngưỡng cảnh báo của `fefo-history`) |

## Biến môi trường

| Biến | Ý nghĩa |
|---|---|
| `SAP_USER_EMAIL`, `SAP_USER_PASS` | Tài khoản SAP. Bắt buộc khi chạy nền và phiên hết hạn |
| `SAP_URL` | Ghi đè `sap.base_url` |
| `SAP_OUTPUT_DIR` | Ghi đè thư mục output |
| `SAP_INPUT_DIR` | Ghi đè thư mục đầu vào |
| `SAP_SESSION_DIR` | Ghi đè thư mục lưu phiên đăng nhập (mặc định `.session/<site>`) |
| `SAP_UNATTENDED` | `1` = ép chế độ chạy nền, `0` = ép chế độ chạy tay |
| `SAP_TEST_MODE`, `SAP_MAX_PAGES` | Tải giới hạn số trang để thử |
| `SAP_PRD_DATE_FORMAT` | `dd/mm` hoặc `mm/dd` để ép kiểu ngày SX nhập tay |
| `SAP_MA_BO_SUNG` | Danh sách mã bổ sung dự phòng khi file txt trống |
| `GOOGLE_APPS_SCRIPT_URL` | URL Web App FEFO |
| `GOOGLE_APPS_SCRIPT_SECRET` | Secret gửi kèm mọi payload |
| `GOOGLE_CAPACITY_SCRIPT_URL` | URL Web App Capacity |

Một máy chạy **nhiều site**: các biến `SAP_OUTPUT_DIR`, `GOOGLE_APPS_SCRIPT_URL`… là biến chung cho cả máy. Vì vậy nên đặt giá trị riêng của từng site trong `sites/<site>.local.toml`, không đặt bằng biến môi trường.
