# Quy tắc nghiệp vụ

Tài liệu này mô tả **chính xác** logic đang chạy. Mọi con số có ghi `(cấu hình: ...)` lấy từ `sites/<site>.toml`; giá trị trong ngoặc là của site HM.

## 1. Tải dữ liệu SAP

- Nguồn: OData `sap.odata_path` trên `sap.base_url`, `?$format=json&sap-client=<sap.client>`. Biến môi trường `SAP_URL` ghi đè `base_url`.
- Phiên đăng nhập lưu ở `.session/<site>/.sap_session.json`. Nếu có phiên thì mở Edge ẩn (headless).
- Phiên hết hạn:
  - Chạy tay (`--interactive`): mở Edge có giao diện, tự điền `#j_username`/`#j_password`, chờ tối đa 120 giây để làm MFA.
  - Chạy nền (Task Scheduler, `SAP_UNATTENDED=1` hoặc không có bàn phím): không bao giờ hỏi bàn phím; thử điền form trong 25 giây, thất bại thì báo lỗi và hướng dẫn chạy `--interactive`.
- Nhận diện trang đăng nhập:
  - Theo hostname: `login.microsoftonline.com`, `accounts.sap.com`, `adfs`, `okta.com`.
  - Theo nội dung trang: `sign in`, `pick an account`, `j_username`, `could not authenticate`.
- Phân trang theo `__next`. Nếu `__next` trỏ lại trang đã tải → dừng, báo lỗi vòng lặp.
- Tự phục hồi:
  - Hết phiên giữa chừng → đăng nhập lại, tối đa `sap.max_relogin_attempts` (2) lần.
  - Lỗi mạng, trang không phải JSON, sai cấu trúc → chờ `incomplete_retry_wait_seconds` (5/15/30 giây) rồi tải tiếp **từ đúng trang đang dừng**, tối đa `max_incomplete_retries` (3) lần.
  - Hết số lần mà vẫn thiếu → dừng lượt chạy, **không xuất báo cáo** (giữ nguyên FEFO lần trước).
- `SAP_TEST_MODE=1` giới hạn `SAP_MAX_PAGES` trang (mặc định `sap.test_max_pages` = 10).
- Có bản ghi trùng `__metadata.id` thì chỉ ghi cảnh báo, không xóa.

## 2. Làm sạch

- Chuỗi `/Date(ms)/` → ngày (lấy dãy số đầu tiên trong ngoặc). Chuỗi `PT#H#M#S` → giờ. Chỉ áp cho cột dạng chữ.
- Giá trị `/Date(...)/` không có số (ví dụ `/Date()/`) được giữ nguyên. Bản v5 dừng hẳn ở trường hợp này (xem CHANGELOG).

## 3. Kiểm kho thực tế (Google Sheet)

- Tải CSV công khai `sources.stock_count_csv_url`. Header ở dòng 2; nếu dòng 2 không có cột vị trí thì thử dòng 1.
- Không tải được hoặc không có cột vị trí → coi như không có dữ liệu kiểm kho:
  - không có vị trí Blocked;
  - không bổ sung mã;
  - không xuất báo cáo đối chiếu.
- **Blocked**: cột `STATUS` có giá trị `block`/`blocked` (không phân biệt hoa thường).
  - Bảng FEFO: loại theo **vị trí**.
  - Audit: theo dõi theo **cặp vị trí + mã hàng**.

## 4. Chuẩn hóa vị trí

1. Gộp khoảng trắng liên tiếp, bỏ khoảng trắng hai đầu, viết HOA.
2. Bỏ tiền tố đầu tiên khớp trong `location.strip_prefixes` (`HMPKG`, `PKG`, `HM`).
3. Nhóm kho: lấy tiền tố đầu tiên khớp trong `location.warehouse_group_prefixes` (`BL`, `F`, `G`, `E`, `D`) → `Kho <tiền tố>`.
   - Không khớp tiền tố nào → `Kho <các chữ cái đầu>`.
   - Không có chữ cái đầu → `Kho Khác`.
   - Vị trí rỗng → `Unknown`.

## 5. Mã bổ sung ngoài SAP

- Danh sách mã lấy từ `Data_Input/SAP_MA_BO_SUNG.txt`:
  - Mã ngăn cách bằng dấu phẩy, chấm phẩy hoặc xuống dòng.
  - Bỏ các dòng bắt đầu bằng `#`.
  - File trống hoặc không có thì mới dùng biến môi trường `SAP_MA_BO_SUNG`.
- Chỉ dòng kiểm kho có mã nằm trong danh sách mới được thêm vào. Dòng thêm vào mang `Data_Source = "Google Sheet (SAP chưa ghi nhận)"`.
- Bỏ dòng kiểm kho đã có trên SAP, so theo bộ ba (vị trí chuẩn hóa, mã, ngày SX). Ngày SX phía SAP là Ngày SX, thiếu thì lấy Ngày nhập kho.
- **Lịch sử vị trí** (`.sap_location_history.json`, giữ `manual.location_history_retention_days` = 7 ngày) dùng để phân biệt:
  - SAP **chưa từng** ghi nhận (vị trí, mã) → SAP bỏ sót → **giữ** dòng kiểm kho.
  - SAP **từng** ghi nhận nhưng nay không còn → hàng đã xuất → **loại** dòng kiểm kho.
  - Chưa có lịch sử (lần chạy đầu) → giữ tất cả.
- Mã có trên Sheet nhưng không có trên SAP và không nằm trong danh sách → chỉ ghi cảnh báo vào log.
- Số lượng của dòng kiểm kho:
  - Ưu tiên cột `Q'TY (Carton/Crate)` nếu > 0. Mọi dấu `.`, `,`, khoảng trắng trong cột này đều là dấu ngăn hàng nghìn (`6.760` = 6760).
  - Nếu không có thì lấy `Qty (PL) × Qty (Carton/Crate)/Pallet`.
  - Hai cách lệch nhau > 50 % thì ghi cảnh báo.
- Loại dòng kiểm kho khi:
  - số lượng ≤ 0;
  - hoặc thiếu hạn dùng (`Local Shelf Life` trống hoặc ≤ 0);
  - hoặc thiếu ngày gốc.
- Ngày SX nhập tay được đọc theo 3 lớp:
  1. Dạng ISO `yyyy-mm-dd`.
  2. `dd/mm` hay `mm/dd`: quyết định theo đa số **cả cột**, ép được bằng `SAP_PRD_DATE_FORMAT`.
  3. Các định dạng phụ (`dd-mm-yyyy`, năm 2 chữ số).

  Ngày lệch quá 2 năm so với hôm nay thì ghi cảnh báo.

## 6. Shelf life và tình trạng tồn

- Ngày gốc = Ngày SX, thiếu thì Ngày nhập kho. Hạn dùng = ngày gốc + `Local Shelf Life` (ngày).
- `% shelf life = (hạn dùng − hôm nay) / Local Shelf Life × 100`, làm tròn 2 chữ số. Shelf life = 0 hoặc thiếu → 0 %.
- Phân loại (cấu hình `[shelf_life]`):

| Điều kiện | Nhãn |
|---|---|
| % ≤ `expired_max` (0) | 6 - Expired |
| % < `near_expiry_below` (30) | 5 - Hàng Cận Date |
| % < `traditional_below` (66) | 4 - Chỉ xuất Kênh TT |
| % < `emart_below` (69) | 3 - Khả dụng Emart |
| % ≤ `supermarket_max` (71) | 2 - Khả dụng Siêu thị |
| còn lại | 1 - Khả dụng Toàn bộ |

- Số pallet = Số lượng / `Qty (Carton/Crate)/Pallet`, làm tròn 2 chữ số.
- Thời gian lưu kho = hôm nay − Ngày nhập kho (thiếu thì lấy Ngày SX).

## 7. Capacity và occupancy

- Nhóm capacity theo đơn vị ở sheet `Unit` của `Capacity.xlsx`:

| Đơn vị chứa | Nhóm |
|---|---|
| `CS`, `CASE`, `TR`, `TRAY` | Capacity Can |
| `CR`, `CRATE` | Capacity Bot |
| `BR`, `KEG`, `PC`, `CO2` | Capacity Keg |
| còn lại | Uncategorized |

- Sức chứa tối đa = cột tương ứng nhóm ở sheet `Capacity`, khớp theo vị trí chuẩn hóa.
- Occupancy % = pallet / sức chứa × 100.
- **Vị trí trống** gửi lên Google Sheet:
  - Vị trí có tổng pallet = 0.
  - Sức chứa lấy từ cột `location.empty_location_capacity_column` (`Capacity Bot`).
  - Loại các vị trí trong `location.empty_location_exclusions` (13 vị trí `FDD1…GDD3`).
  - Sắp theo nhóm kho, rồi theo chỗ trống giảm dần.

## 8. Bảng FEFO

1. Bỏ dòng thiếu vị trí hoặc mã; **bỏ hàng sản xuất hôm nay**.
2. **Gom lô** trong cùng (vị trí, mã):
   - Sắp các lô theo ngày SX. Lô đầu tiên mở nhóm và làm mốc.
   - Lô nào cách **mốc** ≥ `fefo.lot_split_days` (7) ngày thì mở nhóm mới và trở thành mốc mới.
   - Đo từ mốc, không đo từ lô liền trước. Ví dụ các lô ngày 1, 6, 11, 16 tạo 2 nhóm: {1, 6} và {11, 16}.
   - Lô thiếu ngày SX vào nhóm riêng.
3. Số lượng mỗi dòng = tổng nhóm. Ngày SX và % hiển thị = lô có % shelf life thấp nhất trong nhóm.
4. Bỏ vị trí Blocked (so với tên vị trí thuần, **trước** khi gắn `*`).
5. **Bỏ hàng lẻ / hết hàng (v6):**
   - Dòng có tổng số lượng < `fefo.min_quantity` (100 đơn vị cơ sở) bị loại, kể cả dòng bằng 0 hoặc âm.
   - Đặt `min_quantity = 0` để tắt quy tắc này.
6. Sắp xếp theo thứ tự ưu tiên:
   1. `% shelf life` tăng dần.
   2. Khi bằng nhau: dòng SAP trước, dòng kiểm kho sau.
   3. **Số lượng tăng dần (v6):** cùng ngày SX thì bin còn ít hàng hiện trước để dọn trống bin. Bin đang được lấy hàng sẽ nhảy lên đầu và ở đó tới khi hết, tablet không còn cảnh "hiện rồi biến mất".
   4. **Tên vị trí tăng dần (v6):** để thứ tự luôn xác định khi trùng số lượng.
7. Dòng kiểm kho được gắn hậu tố `*` vào tên vị trí.
8. Đầu ra:
   - `FEFO.xlsx`: sheet `fefo.workbook_sheet`, ghi từ dòng `fefo.workbook_start_row` (4). Dữ liệu cũ bị xóa, các ô gộp trong vùng ghi được gỡ gộp.
   - Payload Apps Script:
     - Header 10 cột, cột 10 là thời gian gửi.
     - Ngày định dạng `dd/mm/yyyy`, % định dạng `"xx.xx%"`.

## 9. Đối chiếu SAP ↔ kiểm kho

- Chỉ dùng dòng nguồn SAP. Gom hai phía theo (vị trí chuẩn hóa, mã, ngày SX), rồi nối ngoài (outer join).
- Nhãn trạng thái:

| Trường hợp | Nhãn |
|---|---|
| Hai bên có, lệch < 0,01 PL | Match (Khớp hoàn toàn) |
| Hai bên có, lệch ≥ 0,01 PL | Lệch số lượng (Thực tế: … PL vs SAP: … PL) |
| Chỉ có trên Sheet | Chưa có trên SAP |
| Chỉ có trên SAP | Có trên SAP nhưng kho thực tế không ghi nhận (hoặc lệch ngày SX) |

- Bỏ dòng cả hai phía đều bằng 0. Ghi cảnh báo khi vị trí lệch do ký tự ẩn (zero-width, BOM…).

## 10. Báo cáo tồn kho

- `Inventory_Report_Full.xlsx` bị ghi đè mỗi lượt.
- `Daily_Reports/Inventory_Report_Full_<yyyy-mm-dd>.xlsx` chỉ tạo ở **lượt đầu tiên trong ngày**, không ghi đè.
- File đang mở trong Excel → thử lại 3 lần, mỗi lần cách 3 giây.

## 11. Audit Blocked / Hidden-bin

- Mô phỏng tablet:
  - Bỏ vị trí bắt đầu bằng `display_exclude_prefixes` (`K`, `H`) hoặc chứa `display_exclude_keywords` (`LOOSE`). Hậu tố `*` không ảnh hưởng.
  - Xếp hạng theo % shelf life trong từng mã. Hạng > `fefo.display_max_slots` (6) là **ẩn**.
- Mỗi lô SAP (vị trí, mã, ngày SX) thuộc dòng FEFO có ngày đại diện lớn nhất mà vẫn ≤ ngày của lô.
- **v6:** nếu lô cách ngày đại diện đó ≥ `fefo.lot_split_days` (7) ngày, lô **không** thuộc dòng nào. Nhóm thật của lô đã bị loại khỏi bảng FEFO vì là hàng lẻ, nên không được gán nhầm sang nhóm cũ hơn. Trạng thái lô là `shown`, `hidden`, `excluded` hoặc `not_displayed` (sản xuất hôm nay, hoặc vị trí Blocked).
- **HIDDEN_BIN**: lô đã ẩn **từ lần chạy trước** mà giảm hơn `audit.qty_delta_threshold` (100) đơn vị.
- **BLOCKED**: cặp đang Blocked (hoặc vừa gỡ Blocked) mà số lượng thay đổi, bất kỳ mức nào.
- Xác nhận:
  - Chỉ báo khi thay đổi còn nguyên qua `audit.confirm_runs` (2) lượt liên tiếp, so với mốc trước khi thay đổi.
  - Quá `pending_max_age_minutes` (120) phút, hoặc số lượng tự hồi lại → ghi `transient`, không báo.
- Bảo vệ:
  - Số dòng SAP tụt hơn `max_record_drop_ratio` (5 %) so với lần trước → bỏ so sánh lượt này, tối đa `max_consecutive_suspect` (1) lượt liên tiếp.
  - Gửi lỗi → giữ lại, thử ở các lượt sau, tối đa `max_push_attempts` (3) lần.
- Lưu trữ:
  - `audit/audit_state.json` ghi kiểu nguyên tử (atomic).
  - `audit/audit_log.jsonl` chỉ ghi thêm, không sửa.
  - `audit/history/*.json.gz` giữ `history_retention_days` (7) ngày.
- Lỗi trong audit không làm hỏng lượt chạy.

## 12. Vận hành

- File khóa `.sap_inventory.lock` chống chạy chồng. Khóa cũ hơn `run.lock_stale_hours` (3) giờ thì tự xóa.
- Log ghi ra `logs/sap_inventory.log`, xoay file theo ngày, không tự xóa.
- Cuối mỗi lượt ghi phần tổng kết, ví dụ:

  ```
  Tổng kết lượt chạy:
    sap       THÀNH CÔNG    85.2s
    report    THÀNH CÔNG    21.4s
  Tất cả các bước đã hoàn tất
  ```

  Trạng thái của từng bước có thể là:
  - `THÀNH CÔNG`;
  - `THẤT BẠI`: lỗi, hoặc SAP trả 0 bản ghi;
  - `BỎ QUA`: đang có lượt khác chạy.

  Chỉ khi mọi bước thành công mới có dòng `Tất cả các bước đã hoàn tất`. Báo cáo hiệu năng dựa vào các dòng này.

## 13. Báo cáo hiệu năng (`perf-report`)

- Mỗi dòng `Đã bật ghi log file` mở đầu một lượt chạy. Dòng log không có thời gian (traceback) được nối vào dòng trước.
- Kết quả lượt:
  - `Hoàn tất`: có dòng `Tất cả các bước đã hoàn tất` và không bước nào khác `THÀNH CÔNG`.
  - `Có bước lỗi`: có bước khác `THÀNH CÔNG`.
  - `Dở dang`: không có phần tổng kết.
- **Khoảng đứt:** hai lượt `Hoàn tất` liên tiếp cách nhau > `--nguong-dut` phút (mặc định `monitoring.gap_warning_minutes` = 45). Số lượt bị mất ước tính = khoảng cách / `--chu-ky` − 1, tối thiểu 1.
- **Dữ liệu bất thường:** lượt có số dòng SAP < 95 % trung vị.
- File Excel có 9 sheet: Tổng quan, Theo ngày, Khoảng đứt, Chạy liên tục, Lượt lỗi, Theo giờ, Chất lượng dữ liệu, Cảnh báo trong lượt OK, Chi tiết từng lượt.

## 14. Lịch sử hiển thị E-FEFO (`fefo-history`)

- Đọc các snapshot `audit/history/<yyyymmdd_hhmmss>.json.gz` (giữ 7 ngày). File hỏng được bỏ qua và báo ra màn hình.
- Trong mỗi snapshot:
  - Các lô của mã không bị loại theo tên vị trí được xếp theo % shelf life. Lô cùng % giữ thứ tự trong snapshot.
  - Trạng thái của vị trí theo hạng tốt nhất của nó:
    - `HIỆN` nếu hạng ≤ `fefo.display_max_slots`, còn lại là `ẨN`;
    - `LOẠI` nếu vị trí thuộc K/H/LOOSE;
    - `KHÔNG CÓ` nếu vị trí không có lô nào của mã.
- Khi trạng thái đổi:
  - Liệt kê các lô có % ≤ lô đang theo dõi đã **thêm** hoặc **mất** so với lượt trước.
  - Đổi rồi quay lại ngay ở lượt sau → cảnh báo nghi số liệu SAP nhảy tạm.
- Cảnh báo dữ liệu:
  - Lượt bị đánh dấu nghi tải thiếu.
  - Số bản ghi SAP tụt > `audit.max_record_drop_ratio` (5 %).
  - Hai snapshot cách nhau > `monitoring.gap_warning_minutes` (45 phút).
