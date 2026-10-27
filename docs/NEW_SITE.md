# Nhân rộng sang site mới

Ví dụ thêm site `dn`.

## 1. Tạo cấu hình

```bat
.venv\Scripts\python -m efefo new-site dn
```

Lệnh này tạo `sites\dn.toml` từ `sites\_template.toml`. Sửa các khóa sau:

| Khóa | Lấy thông tin ở đâu |
|---|---|
| `sap.base_url`, `sap.client` | Tenant S/4HANA của site |
| `sap.odata_path` | Giữ nguyên nếu site dùng cùng service `ZUI_IM_BCTKTTT_O2` |
| `paths.onedrive_subdir` | Thư mục SharePoint/OneDrive của site |
| `sources.stock_count_csv_url` | Google Sheet kiểm kho của site → File → Share → Publish to web → CSV |
| `location.strip_prefixes` | Tiền tố bin SAP của site (ví dụ `DNPKG`, `PKG`, `DN`) |
| `location.warehouse_group_prefixes` | Các khu kho của site |
| `location.display_exclude_*` | Khu không lên tablet |
| `location.empty_location_exclusions` | Vị trí không báo trống |
| `[publish]` | Đặt `false` nếu site không dùng Apps Script |

Ngưỡng shelf life, FEFO và audit giữ như HM, trừ khi site có quy định khác.

## 2. Secret và giá trị riêng máy

Tạo `sites\dn.local.toml` (file này không đưa lên git):

```toml
[publish]
secret = "..."
fefo_script_url = "https://script.google.com/macros/s/.../exec"
```

## 3. Dữ liệu đầu vào

Trong thư mục output của site:

```
Data_Input\Shelflife.xlsx     cột: Iteam, Short Name, Name, Unit, Qty (Carton/Crate)/Pallet, Local Shelf Life
Data_Input\Capacity.xlsx      sheet Capacity: Location, Capacity Can, Capacity Bot, Capacity Keg
                              sheet Unit: Material, Unit
Data_Input\SAP_MA_BO_SUNG.txt mã ngoài SAP, mỗi dòng một mã hoặc ngăn cách bằng dấu phẩy
FEFO.xlsx                     mẫu có sheet "Update Actual Count", dữ liệu ghi từ dòng 4
```

## 4. Kiểm tra và chạy lần đầu

```bat
.venv\Scripts\python -m efefo check --site dn
scripts\run_site.bat dn --interactive
```

Lần đầu chưa có lịch sử vị trí và mốc audit, nên:
- giữ lại mọi dòng kiểm kho;
- audit chỉ ghi mốc, chưa báo sự kiện.

## 5. Apps Script và tablet (nếu site dùng E-FEFO trên tablet)

Làm theo [APPS_SCRIPT.md](APPS_SCRIPT.md). Trước khi dán code, sửa các giá trị riêng của site trong `Code.gs` và `Index.html`:
- `HISTORY_SHEET_ID`;
- `DEVICE_NAMES`, `ITEM_NOTES`, dòng hướng dẫn kênh bán;
- `validSecrets`;
- danh sách vị trí loại trừ.

Giữ bản đã sửa cho site trong `apps_script/<site>/` để không ghi đè bản của HM.

## 6. Lập lịch

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Site dn -EveryMinutes 60
```

## 7. Đưa cấu hình lên git

Commit `sites\dn.toml`. Không commit `sites\dn.local.toml` (đã có trong `.gitignore`).
