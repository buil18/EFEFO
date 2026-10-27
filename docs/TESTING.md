# Kiểm thử

## Chạy test

```bat
.venv\Scripts\python -m pytest tests\unit
.venv\Scripts\python -m pytest tests\stress -s
set EFEFO_LEGACY_SCRIPT=C:\...\SAP_FULL_27_8_v6.py
set EFEFO_LEGACY_PERF_SCRIPT=C:\...\bao_cao_hieu_nang_pad.py
set EFEFO_LEGACY_HISTORY_SCRIPT=C:\...\kiem_tra_lich_su_fefo.py
set EFEFO_REAL_INPUT_DIR=C:\...\Data_Input
.venv\Scripts\python -m pytest tests\parity
```

Test đối chứng (`tests\parity`) cần các biến môi trường trỏ tới script gốc. Thiếu biến nào thì các test tương ứng tự bỏ qua (skip):
- `EFEFO_LEGACY_SCRIPT`: đường dẫn `SAP_FULL_27_8_v6.py` gốc.
- `EFEFO_LEGACY_PERF_SCRIPT`, `EFEFO_LEGACY_HISTORY_SCRIPT`: đường dẫn hai công cụ gốc.
- `EFEFO_REAL_INPUT_DIR`: thư mục chứa Shelflife/Capacity thật, chỉ cần cho test dùng master thật.

Không test nào gọi SAP hay Google thật. SAP, Google Sheet và Apps Script đều được thay bằng bản giả trong `tests\support\fakes.py`. Dữ liệu được sinh ngẫu nhiên có kiểm soát (seed cố định) bởi `tests\support\scenario.py`.

## Ba lớp kiểm thử

| Lớp | Số test | Mục tiêu |
|---|---|---|
| `tests/unit` | 142 | Từng quy tắc nghiệp vụ (gồm 3 quy tắc mới của v6), biên ngưỡng, xử lý lỗi, kịch bản QA đầu-cuối, hai công cụ |
| `tests/parity` | 37 | Bản mới cho kết quả **giống hệt** `SAP_FULL_27_8_v6.py` (25 test) và hai công cụ gốc (12 test) |
| `tests/stress` | 18 | Tải lớn, khả năng mở rộng, dữ liệu hỏng (fuzz), chạy liên tục 48 lượt |

Lần chạy gần nhất: **197/197 đạt** (khoảng 5 phút).

### Test đối chứng với pipeline gốc — cách so sánh

Mỗi kịch bản chạy `SAP_FULL_27_8_v6.py` gốc và bản mới trên **cùng** dữ liệu và **cùng** thời điểm (đồng hồ được cố định). Sau mỗi lượt, test so sánh:

- Từng ô của mọi file Excel: báo cáo tồn, bản chốt ngày, đối chiếu, FEFO.xlsx (kể cả dòng tiêu đề và ô gộp của file mẫu).
- `sap_response_full.json`, `.sap_location_history.json`, `audit/audit_state.json`, `audit/audit_log.jsonl`, `audit/history/*.json.gz`.
- Toàn bộ payload gửi Apps Script (FEFO, vị trí trống, audit): đúng thứ tự, đúng từng giá trị.

| Kịch bản | Nội dung |
|---|---|
| `test_single_run_identical[0..11]` | 12 bộ dữ liệu ngẫu nhiên, 1 lượt |
| `test_multi_run_audit_identical[4 seed]` | 7 lượt liên tiếp: giảm số lượng, hồi lại, mất 30 % dòng (nghi tải thiếu), sang ngày mới. Kiểm tra cơ chế xác nhận và gửi lại audit |
| `test_without_manual_master_and_template` | Mã bổ sung không có master, không có file FEFO.xlsx |
| `test_stock_count_unavailable` | Google Sheet kiểm kho sai cấu trúc |
| `test_large_dataset_identical` | 6.000 dòng SAP, 800 dòng kiểm kho, 2 lượt |
| `test_real_master_files_identical` | Shelflife/Capacity **thật** của HM, 3.000 dòng, 2 lượt |
| `test_malformed_records_identical[0..3]` | Dữ liệu SAP lỗi định dạng (fuzz), 2 lượt |
| `test_known_legacy_crash_on_empty_sap_date_is_fixed` | Ghi nhận lỗi của script gốc đã được sửa (xem CHANGELOG) |

Bộ test này chạy đạt với cả v5 (bản 1.0) lẫn v6 (bản 1.1). Với v6, các kịch bản đã tự đi qua 3 quy tắc mới vì dữ liệu sinh ra có nhiều nhóm lô tổng < 100 và nhiều lô trùng %.

### Test đối chứng hai công cụ

| Kịch bản | Nội dung |
|---|---|
| `test_perf_report_identical[4 bộ]` | Log 4 ngày sinh ngẫu nhiên: lượt thành công, tải lại, cảnh báo, thiếu cấu hình Google Script, lỗi có traceback, dở dang, khoảng đứt 1–3 giờ, file log xoay theo ngày, dòng rác trước lượt đầu. So từng ô của 9 sheet và nội dung in ra màn hình. Có lọc `--tu/--den` và đổi `--chu-ky/--nguong-dut` |
| `test_perf_report_on_real_pipeline_logs` | Log do chính pipeline mới ghi ra (6 lượt, 1 lượt SAP trả 0 dòng) được đọc đúng bởi script gốc lẫn bản mới |
| `test_fefo_history_identical[7 bộ]` | Snapshot audit thật từ 12 lượt chạy (thiếu 2 lượt, 1 lượt tụt 12 % dòng, 2 file hỏng), 3 mã × 3 vị trí + 1 vị trí không tồn tại, nhập vị trí chữ thường có `*`. Các tùy chọn: mặc định, `--all`, `--chi-tiet`, cả hai, `--date`, `--from/--to`, ngày không có dữ liệu |

`fefo-history`: script gốc lấy danh sách lô "thêm/mất" từ phép trừ tập hợp (`set`), nên khi nhiều lô trùng %, thứ tự in **thay đổi ngẫu nhiên giữa các lần chạy** ngay cả với script gốc. Bản mới in theo thứ tự trong snapshot (ổn định). Test so sánh các dòng này mà không xét thứ tự; mọi dòng khác phải trùng từng ký tự.

Dữ liệu sinh ra cố ý chứa các trường hợp biên:
- bin có tiền tố HMPKG/PKG/HM, chữ thường, khoảng trắng thừa, ký tự ẩn `\u200b`;
- vị trí K/H/LOOSE;
- lô sản xuất hôm nay, lô thiếu ngày SX hoặc ngày nhập;
- lô cách nhau 1–10 ngày để thử ngưỡng tách lô 7 ngày;
- số lượng lẻ (12.5, 0.333…);
- trùng `__metadata.id`;
- ngày SX nhập tay đủ 4 định dạng;
- `Q'TY` dạng `6.760` / `1,250`;
- STATUS `Blocked`/`block`;
- mã có đuôi `.0`.

## Danh sách QA test case

| ID | Kịch bản | Kết quả mong đợi | Test |
|---|---|---|---|
| QA01 | Lượt chạy đầu tiên, đủ đầu vào | Tạo đủ 8 loại file; khóa được xóa; payload FEFO được gửi | `test_qa01_first_run_creates_every_output` |
| QA02 | Chạy lần 2 trong cùng ngày | Bản chốt đầu ngày giữ nguyên, báo cáo mới nhất được ghi đè | `test_qa02_daily_snapshot_not_overwritten_same_day` |
| QA03 | Bản chốt ngày tạo bằng cách chép file | Nội dung giống báo cáo mới nhất | `test_qa03_daily_snapshot_identical_to_latest` |
| QA04 | SAP trả 0 bản ghi | Dừng, không tạo báo cáo, không để lại khóa | `test_qa04_no_records_stops_without_outputs` |
| QA05 | Đang có lượt khác chạy | Bỏ qua lượt này, giữ khóa của lượt kia | `test_qa05_active_lock_skips_run` |
| QA06 | Thiếu file mẫu FEFO.xlsx | Vẫn gửi Google Sheet, không tạo FEFO.xlsx | `test_qa06_missing_template_still_publishes` |
| QA07 | Tắt cả 3 cờ publish | Không có request mạng nào, báo cáo vẫn tạo | `test_qa07_publish_switches_off_means_no_network` |
| QA08 | Mất mạng khi gửi | Báo cáo vẫn tạo; sự kiện audit giữ lại để gửi sau | `test_qa08_network_down_keeps_reports_and_queues_audit` |
| QA09 | Không tải được Google Sheet kiểm kho | Không đối chiếu, không Blocked; FEFO vẫn tạo | `test_qa09_stock_count_unreachable` |
| QA10 | Ghi FEFO.xlsx | Giữ 3 dòng tiêu đề, xóa dữ liệu cũ, số dòng đúng | `test_qa10_fefo_workbook_layout` |
| QA11 | Định dạng payload FEFO | Header 10 cột + giờ; % dạng `xx.xx%` tăng dần | `test_qa11_fefo_payload_contract` |
| QA12 | Thứ tự FEFO khi trùng % | Dòng SAP luôn trước dòng kiểm kho `*` | `test_qa12_manual_rows_never_outrank_fresher_sap_rows` |
| QA13 | Phiên SAP hết hạn giữa chừng | Đăng nhập lại, tải tiếp, không trùng bản ghi | `test_recovery_relogs_in_on_expiry` |
| QA14 | SAP lỗi tạm thời 2 lần | Chờ 5 s, 15 s rồi tải tiếp từ trang dừng | `test_recovery_resumes_after_transient_errors_without_duplicates` |
| QA15 | SAP lỗi liên tục | Dừng sau 3 lần, không xuất báo cáo | `test_recovery_gives_up_after_limit` |
| QA16 | `__next` trỏ vòng lặp | Báo lỗi, không lặp vô hạn | `test_pagination_loop_detected` |
| QA17 | Cấu hình site sai khóa/kiểu/ngưỡng | Dừng, chỉ rõ khóa sai | `tests/unit/test_config.py` |
| QA18 | Thiếu Shelflife/Capacity | `check` báo lỗi, `run` dừng | `test_check_site_reports_missing_inputs` |
| QA19 | Excel đang mở (bị khóa) | Thử lại 3 lần rồi mới bỏ qua | `test_excel_write_retries_when_locked` |
| QA20 | Khóa chạy trùng cũ hơn 3 giờ | Tự xóa và chạy tiếp | `test_stale_lock_is_replaced` |
| QA21 | Lô ẩn giảm > 100 qua 2 lượt | Báo HIDDEN_BIN đúng định dạng 10 cột | `test_change_needs_two_runs_then_confirms`, `test_event_row_format` |
| QA22 | Số lượng tự hồi lại / chờ quá 120 phút | Ghi transient, không báo | `test_change_that_recovers_is_transient`, `test_stale_pending_expires` |
| QA23 | Số dòng SAP tụt > 5 % | Bỏ so sánh 1 lượt | `test_suspect_run_detection` |
| QA24 | Vị trí SAP đã hết hàng nhưng kiểm kho còn dòng | Loại dòng kiểm kho | `test_history_drops_rows_whose_bin_emptied_in_sap` |
| QA25 | File lịch sử vị trí hỏng | Bỏ qua, giữ mọi dòng kiểm kho | `test_corrupt_history_is_ignored` |
| QA26 | Dòng FEFO tổng < 100, bằng 0, âm (v6) | Bị loại; `min_quantity = 0` thì giữ | `test_v6_small_rows_dropped_and_ties_sorted_by_quantity_then_location`, `test_v6_min_quantity_zero_disables_filter` |
| QA27 | Nhiều bin cùng % shelf life (v6) | Bin ít hàng trước, trùng số lượng thì theo tên vị trí; dòng `*` luôn sau | như trên |
| QA28 | Lô SAP cách nhóm FEFO gần nhất ≥ 7 ngày (v6) | Không gán vào nhóm cũ hơn | `test_v6_lot_far_from_group_anchor_is_not_assigned` |
| QA29 | Lượt thành công, lượt lỗi, SAP trả 0 dòng, đang có lượt khác chạy | Log ghi tổng kết; `perf-report` phân loại đúng Hoàn tất / Có bước lỗi (`BỎ QUA`) | `test_runner_writes_step_summary_for_perf_report` |
| QA30 | Log có traceback, lượt dở dang | Traceback nối vào dòng trước; lượt không có tổng kết là "Dở dang" | `test_perf_run_classification` |
| QA31 | Thư mục log trống / không có lượt chạy | Báo lỗi rõ ràng, không tạo file | `test_perf_report_errors` |
| QA32 | Vị trí đi qua đủ 4 trạng thái HIỆN/ẨN/LOẠI/KHÔNG CÓ, có lượt nghi tải thiếu và khoảng trống 2 giờ | Đúng khoảng thời gian, giải thích, cảnh báo, bảng xếp hạng | `test_history_states_and_explanations` |
| QA33 | Nhập sai thời gian, thư mục không tồn tại, khoảng ngày không có snapshot | Báo lỗi / thông báo, không dừng bất thường | `test_history_inputs` |

## Stress và hiệu năng

Đo trên máy test (Linux, 1 tiến trình), dữ liệu sinh ngẫu nhiên với 80 vị trí mỗi khu:

| Kịch bản | Kết quả |
|---|---|
| 20.000 dòng SAP, toàn pipeline | 14 giây, 3.182 dòng FEFO sau khi loại dòng < 100 (ngưỡng đạt: < 90 giây) |
| 4.000 → 16.000 dòng (gấp 4) | 3,5 s → 11,5 s (gấp 3,3): thời gian tăng tuyến tính |
| 48 lượt liên tiếp (2 ngày, mỗi giờ 1 lượt) | Trung bình 0,69 s/lượt, 154 sự kiện audit, không lượt nào chậm bất thường, state/jsonl luôn hợp lệ |
| 8 bộ dữ liệu SAP lỗi định dạng | Không lượt nào dừng, luôn tạo báo cáo |
| 7 kiểu CSV kiểm kho hỏng (rỗng, thiếu cột, ngày 31/02…) | Không lượt nào dừng |

### Tối ưu so với script gốc (kết quả đầu ra không đổi — đã kiểm chứng bằng test đối chứng)

Đo với 30.000 dòng:

| Bước | Trước | Sau | Cách làm |
|---|---|---|---|
| Ghi báo cáo tồn + bản chốt ngày | 44,4 s | 14,6 s | Ghi bằng `xlsxwriter` (nếu đã cài); bản chốt ngày chép từ file vừa ghi, không ghi lần 2 |
| Chuyển ngày SAP `/Date()/` | 5,3 s | 0,4 s | Xử lý cả cột một lần (vector hóa); trường hợp lạ quay về cách cũ |
| Trạng thái lô trong audit | 4,3 s | 1,3 s | Gom nhóm trên đúng các cột cần dùng; vẫn cộng tuần tự để kết quả số thực khớp tuyệt đối với script gốc |
| Tổng hợp FEFO | 3 lần/lượt | 1 lần/lượt | Dùng lại kết quả cho FEFO.xlsx, Google Sheet và audit |
| **Tổng** | **67 s** | **31 s** | |

Lưu ý: hàm cộng nhanh `groupby().sum()` của pandas dùng thuật toán cộng bù sai số. Khi số lượng là số lẻ, kết quả lệch script gốc ở chữ số thập phân cuối (564/19.000 nhóm). Vì vậy audit vẫn cộng tuần tự từng nhóm.

## Giới hạn đã biết

- Phần đăng nhập Playwright (`sap/client.py`, `sap/auth.py`) chưa chạy được với SAP thật trong môi trường test. Logic phân trang và phục hồi đã có test với trang giả, còn luồng đăng nhập/MFA cần thử trên máy thật bằng `--interactive`.
- Dữ liệu có Material kiểu số lẫn kiểu chữ trong cùng cột (SAP OData không trả như vậy) làm sắp xếp lỗi ở cả script gốc lẫn bản mới.
