# AI Setup Prompt for SynapzCore

Bạn là một AI Coding Agent mới tham gia phát triển dự án **SynapzCore**. Nhiệm vụ đầu tiên của bạn là **TỰ ĐỘNG THIẾT LẬP VÀ CẤU HÌNH TOÀN BỘ WORKSPACE** để đưa dự án vào trạng thái hoạt động mà không cần sự can thiệp thủ công từ Bố (User), tuân thủ các bước dưới đây.

---

## BƯỚC 1: ĐỌC VÀ KHÁM PHÁ CONTEXT (AUTO-DISCOVERY)
1. Đọc file `AGENTS.md` ở root để hiểu kiến trúc 2-AI, các MCP tools và các quy tắc hoạt động.
2. Đọc file `Agent_Profiles/How_We_Work.md` để hiểu quy trình làm việc.
3. Chạy lệnh kiểm tra cấu trúc thư mục để đảm bảo mọi thư mục cốt lõi đều tồn tại:
   - `crates/synapz-memory`, `crates/synapz-tools`, `crates/synapz-mcp`
   - `grok2api_local`

---

## BƯỚC 2: TỰ ĐỘNG THIẾT LẬP PYTHON VIRTUAL ENVIRONMENT (grok2api_local)
1. Di chuyển vào thư mục `E:\AGT_Brain\grok2api_local`.
2. Kiểm tra xem thư mục `venv` đã tồn tại chưa. Nếu chưa:
   - Tạo virtual environment: `python -m venv venv`
3. Kích hoạt venv và cập nhật pip:
   - Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
   - Windows (CMD): `.\venv\Scripts\activate.bat`
4. Cài đặt các thư viện cần thiết. Tìm file `requirements.txt` hoặc `pyproject.toml` trong `grok2api_local` và chạy:
   - `pip install -r requirements.txt` (hoặc lệnh tương ứng).

---

## BƯỚC 3: TỰ ĐỘNG THIẾT LẬP NODE.JS (grok_cookie_refresh)
1. Di chuyển vào thư mục `E:\AGT_Brain\scripts\grok_cookie_refresh`.
2. Chạy lệnh cài đặt các package phụ thuộc:
   - `npm install`
3. Đảm bảo các thư viện như `ws` và các công cụ CDP cần thiết được cài đặt đầy đủ mà không bị lỗi.

---

## BƯỚC 4: BUILD RUST WORKSPACE
1. Trở lại thư mục root `E:\AGT_Brain`.
2. Chạy lệnh build toàn bộ Rust workspace để sinh ra các binary (`synapz-mcp`):
   - `cargo build`
3. Nếu phát hiện lỗi biên dịch, hãy tự động sửa đổi mã nguồn (tối đa 3 lần) hoặc kiểm tra phiên bản Rust toolchain (dự án dùng Rust 2024).

---

## BƯỚC 5: KIỂM TRA & KHỞI TẠO FILE CONFIGS
Kiểm tra và tạo các file cấu hình từ template nếu chưa có sẵn:
1. **Supabase Config**: Kiểm tra file `E:\AGT_Brain\data\supabase_config.json`. Nếu chưa có, tạo file template và thông báo cho Bố điền các credentials cần thiết:
   ```json
   {
     "supabase_url": "YOUR_SUPABASE_URL",
     "supabase_key": "YOUR_SUPABASE_KEY"
   }
   ```
2. **Grok2API Config**: Kiểm tra file `E:\AGT_Brain\grok2api_local\data\config.toml`. Nếu chưa có, tạo cấu hình mặc định:
   ```toml
   app_key = "grok2api"
   # Thêm các cấu hình mặc định khác từ tài liệu
   ```

---

## BƯỚC 6: KHỞI TẠO CHỈ MỤC TRÍ TUỆ CODE (GITNEXUS INDEX)
1. Đảm bảo GitNexus đã được cài đặt và thiết lập.
2. Chạy lệnh phân tích để cập nhật cơ sở dữ liệu đồ thị gọi (call graph) của code:
   - `npx gitnexus analyze`
3. Kiểm tra file `.gitnexus/meta.json` để xác nhận việc lập chỉ mục thành công.

---

## BƯỚC 7: CHẠY KIỂM TRA HỆ THỐNG (HEALTH CHECKS)
Chạy thử các tác vụ để đảm bảo thiết lập hoạt động hoàn hảo:
1. Khởi động thử `grok2api` server trong background:
   - Lệnh: `.\venv\Scripts\granian.exe --interface asgi --host 127.0.0.1 --port 8000 --workers 1 app.main:app`
2. Kiểm tra API endpoint:
   - `curl http://127.0.0.1:8000/v1/models`
3. Chạy test thử kết nối Supabase Cloud thông qua crate `synapz-memory` hoặc MCP tool `grok_health` để xác nhận kết nối mạng thông suốt.

---

## BÁO CÁO KẾT QUẢ CHO BỐ
Khi hoàn tất, hãy xuất một báo cáo ngắn gọn theo định dạng Markdown hiển thị trạng thái của từng phần (✅ Thành công / ❌ Lỗi kèm giải pháp). Tự động đề xuất các bước khắc phục nếu có lỗi xảy ra.
