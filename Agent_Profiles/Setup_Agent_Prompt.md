# AI Setup Prompt for SynapzCore

Bạn là một AI Coding Agent mới tham gia phát triển dự án **SynapzCore**. Nhiệm vụ đầu tiên của bạn là **TỰ ĐỘNG THIẾT LẬP VÀ CẤU HÌNH TOÀN BỘ WORKSPACE** để đưa dự án vào trạng thái hoạt động mà không cần sự can thiệp thủ công từ Bố (User), tuân thủ các bước dưới đây.

---

## BƯỚC 1: ĐỌC VÀ KHÁM PHÁ CONTEXT (AUTO-DISCOVERY)
1. Đọc file `AGENTS.md` ở root để hiểu kiến trúc, các MCP tools và các quy tắc hoạt động.
2. Đọc file `Agent_Profiles/How_We_Work.md` để hiểu quy trình làm việc.
3. Chạy lệnh kiểm tra cấu trúc thư mục để đảm bảo mọi thư mục cốt lõi đều tồn tại:
   - `crates/synapz-memory`, `crates/synapz-tools`, `crates/synapz-mcp`

---

## BƯỚC 2: BUILD RUST WORKSPACE
1. Ở thư mục root `E:\AGT_Brain`.
2. Chạy lệnh build toàn bộ Rust workspace để sinh ra các binary (`synapz-mcp`):
   - `cargo build`
3. Nếu phát hiện lỗi biên dịch, hãy tự động sửa đổi mã nguồn (tối đa 3 lần) hoặc kiểm tra phiên bản Rust toolchain (dự án dùng Rust 2024).

---

## BƯỚC 3: KIỂM TRA & KHỞI TẠO FILE CONFIGS
Kiểm tra và tạo các file cấu hình từ template nếu chưa có sẵn:
1. **Supabase Config**: Kiểm tra file `E:\AGT_Brain\data\supabase_config.json`. Nếu chưa có, tạo file template và thông báo cho Bố điền các credentials cần thiết:
   ```json
   {
     "supabase_url": "YOUR_SUPABASE_URL",
     "supabase_key": "YOUR_SUPABASE_KEY"
   }
   ```

---

## BƯỚC 4: KHỞI TẠO CHỈ MỤC TRÍ TUỆ CODE (GITNEXUS INDEX)
1. Đảm bảo GitNexus đã được cài đặt và thiết lập.
2. Chạy lệnh phân tích để cập nhật cơ sở dữ liệu đồ thị gọi (call graph) của code:
   - `npx gitnexus analyze`
3. Kiểm tra file `.gitnexus/meta.json` để xác nhận việc lập chỉ mục thành công.

---

## BƯỚC 5: CHẠY KIỂM TRA HỆ THỐNG (HEALTH CHECKS)
Chạy thử các tác vụ để đảm bảo thiết lập hoạt động hoàn hảo:
1. Chạy test thử kết nối Supabase Cloud thông qua crate `synapz-memory` để xác nhận kết nối mạng thông suốt.

---

## BÁO CÁO KẾT QUẢ CHO BỐ
Khi hoàn tất, hãy xuất một báo cáo ngắn gọn theo định dạng Markdown hiển thị trạng thái của từng phần (✅ Thành công / ❌ Lỗi kèm giải pháp). Tự động đề xuất các bước khắc phục nếu có lỗi xảy ra.
