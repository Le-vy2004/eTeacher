# 🎓 eTeacher - Facebook Lead Collector & Smart Data Engine
> **Tài liệu tổng quan toàn bộ dự án, kiến trúc, luồng xử lý và lộ trình phát triển cho phiên làm việc tiếp theo.**

---

## 📌 1. TỔNG QUAN DỰ ÁN
`eTeacher` là hệ thống tự động hóa thu thập, bóc tách và quản lý nhu cầu tìm kiếm gia sư từ các Nhóm/Trang Facebook. 

Khác biệt với các công cụ cào bài thông thường chỉ scroll feed chính, `eTeacher` trang bị:
1. **Khả năng quét lùi 30 ngày (1 tháng)** bằng Facebook Group Search Query kết hợp bộ lọc thời gian bài mới nhất (*Chronosort*).
2. **Bộ làm sạch & Bóc tách dữ liệu chuyên sâu (Data Cleaner Engine)**: Tự động chuẩn hóa SĐT, tạo link nhắn Zalo 1-click, trích xuất ngân sách min/max/đơn vị, chuẩn hóa môn học/khối lớp và lọc spam/trung tâm môi giới.
3. **Google Sheets Smart Dashboard**: Đồng bộ 13 cột dữ liệu tương tác cao kèm link Zalo bấm trực tiếp và chống trùng lặp dữ liệu.

---

## 🏗️ 2. KIẾN TRÚC HỆ THỐNG & LUỒNG XỬ LÝ (DATA PIPELINE)

```
[ sources.txt / SQLite Sources ]
             ↓
[ Selenium Chrome Collector (Group Search URL + Chronosort) ]
             ↓ (Raw Facebook Posts lùi 30 ngày)
[ Keyword Filter (Lọc bài có nhu cầu gia sư) ]
             ↓
[ Data Cleaner & Normalizer Engine (cleaner.py) ]
   ├── Chuẩn hóa SĐT (xử lý 'o98...', '098.I23.456')
   ├── Tạo URL Zalo Direct: https://zalo.me/{phone}
   ├── Parse Budget: min_budget, max_budget, budget_unit
   ├── Taxonomy: Môn Học (Toán, Lý, Anh...) & Khối Lớp (Lớp 1-12, Luyện Thi)
   └── Classify: Phụ huynh/Học sinh vs Trung tâm/Môi giới vs Gia sư nhận lớp
             ↓
[ SQLite Deduplication Store (leads.db) ]
             ↓ (Kiểm tra chống lặp theo post_url)
[ Google Sheets Smart Dashboard (13 cột + Hyperlinks) ]
```

---

## 📂 3. CẤU TRÚC MÃ NGUỒN & DANH SÁCH FILE

```text
eTeacher/
├── README.md                           # Hướng dẫn setup cơ bản
├── PROJECT_SUMMARY.md                  # File tổng quan toàn bộ dự án này
├── main.py                             # Wrapper gọi entrypoint chính
│
└── facebook_lead_collector/
    ├── main.py                         # Entrypoint chính chạy pipeline thu thập
    ├── config.py                       # Quản lý cấu hình .env (Pydantic Settings)
    ├── setup_chrome_profile.py         # Khởi tạo & đăng nhập Chrome Profile FB lần đầu
    ├── requirements.txt                # Thư viện phụ thuộc (selenium, pydantic, gspread, v.v.)
    │
    ├── collectors/                     # Module thu thập dữ liệu
    │   ├── base.py                     # BaseCollector interface
    │   ├── facebook.py                 # Facebook collector cơ bản
    │   └── selenium_facebook.py        # Chrome Collector dùng Group Search URL (quét 30 ngày)
    │
    ├── filters/                        # Module lọc & bóc tách dữ liệu
    │   ├── keyword_filter.py           # Bộ lọc từ khóa nhu cầu
    │   └── cleaner.py                  # [MỚI] Engine bóc tách SĐT, Zalo, Budget, Môn/Lớp, Spam
    │
    ├── models/                         # Data Models
    │   └── post.py                     # FacebookPost & Lead Model (chứa to_sheet_row())
    │
    ├── database/                       # Module lưu trữ local
    │   └── sqlite_db.py                # SQLite (leads.db) + Tự động Migration schema
    │
    ├── sheets/                         # Module đồng bộ Google Sheets
    │   └── google_sheets.py            # GoogleSheetsClient (Sync 13 cột + Hyperlinks)
    │
    ├── tests/                          # Automated Test Suite
    │   ├── test_cleaner.py             # Test đơn vị bóc tách SĐT, Zalo, Budget, Taxonomy
    │   └── test_pipeline_integration.py# Test tích hợp luồng pipeline end-to-end
    │
    ├── data/                           # Dữ liệu runtime (gitignored)
    │   ├── sources.txt                 # Danh sách URL Nhóm/Trang FB cần quét
    │   └── leads.db                    # Cơ sở dữ liệu SQLite local
    │
    └── profiles/                       # Thư mục chứa Chrome Profile FB đã đăng nhập
        └── chrome_profile/
```

---

## 📊 4. ĐỊNH DẠNG DỮ LIỆU GOOGLE SHEETS (13 CỘT)

Bảng Google Sheets được đồng bộ với 13 cột chuẩn hóa:

| Cột | Tên Tiêu Đề | Mô Tả Dữ Liệu | Ví Dụ |
| :---: | :--- | :--- | :--- |
| A | `💬 Chat Zalo Direct` | Link công thức `=HYPERLINK(...)` bấm 1-click nhắn Zalo | `💬 Chat Zalo` |
| B | `Số Điện Thoại` | SĐT 10 số đã chuẩn hóa | `0987654321` |
| C | `Môn Học` | Môn học bóc tách theo Taxonomy | `Toán`, `Ngoại Ngữ (Tiếng Anh)` |
| D | `Khối Lớp` | Khối lớp bóc tách theo Taxonomy | `Lớp 12`, `Luyện Thi ĐH` |
| E | `Ngân Sách (VND)` | Học phí bóc tách hiển thị đẹp | `300,000đ/buổi`, `150,000đ - 200,000đ/giờ` |
| F | `🔗 Link Bài FB` | Link công thức `=HYPERLINK(...)` mở bài viết FB | `🔗 Xem bài viết` |
| G | `Tên Người Đăng` | Tên người đăng bài | `Nguyễn Văn A` |
| H | `Thời Gian Đăng` | Thời gian đăng bài | `2026-09-21 14:00:00` |
| I | `Nội Dung Bài Đăng` | Nội dung văn bản gốc bài viết | `Cần gia sư dạy Toán lớp 12...` |
| J | `Nhóm Facebook` | Tên nhóm Facebook | `Hội Gia Sư Hà Nội` |
| K | `Từ Khóa` | Từ khóa tìm kiếm khớp bài viết | `cần gia sư, tìm gia sư` |
| L | `Thời Gian Thu Thập` | Timestamp khi hệ thống cào dữ liệu | `2026-09-21 21:40:00` |
| M | `Phân Loại` | Loại bài viết | `Phụ huynh / Học sinh` hoặc `Trung tâm / Môi giới` |

---

## ⚡ 5. HƯỚNG DẪN VẬN HÀNH (COMMANDS)

### Bước 1: Khởi động Chrome Profile & Đăng nhập Facebook (Chạy 1 lần đầu)
```bash
python facebook_lead_collector/setup_chrome_profile.py
```
*(Đăng nhập tài khoản Facebook trên cửa sổ Chrome mở ra, sau đó bấm ENTER tại terminal)*.

### Bước 2: Chạy thu thập dữ liệu (Single Run)
```bash
python facebook_lead_collector/main.py
```

### Bước 3: Chạy quét định kỳ tự động (ví dụ 30 phút/lần)
```bash
python facebook_lead_collector/main.py --schedule 30
```

### Bước 4: Chạy kiểm thử tự động hệ thống (Test Suite)
```bash
python facebook_lead_collector/tests/test_cleaner.py
python facebook_lead_collector/tests/test_pipeline_integration.py
```

---

## ✅ 6. TRẠNG THÁI HIỆN TẠI (COMPLETED STATUS)
- [x] Đã xong bộ làm sạch `filters/cleaner.py` (Bóc SĐT, Zalo Link, Parse Budget, Môn/Lớp, Lọc Spam).
- [x] Đã nâng cấp `models/post.py` và `database/sqlite_db.py` (Schema migration tự động).
- [x] Đã nâng cấp `sheets/google_sheets.py` (13 Cột + Direct Hyperlinks Zalo & FB).
- [x] Đã nâng cấp `collectors/selenium_facebook.py` (Điều hướng Group Search URL với filter bài mới nhất lùi 30 ngày).
- [x] Đã qua 100% các bài test tự động đơn vị và tích hợp.

---

## 🎯 7. LỘ TRÌNH PHÁT TRIỂN TIẾP THEO (FOR NEXT SESSION)
1. **Tích hợp Telegram Bot Real-time Alert**:
   - Khi phát hiện Lead "Nóng" (Có SĐT + Đăng bài trong 24h + Ngân sách cao), tự động đẩy notification về Telegram kèm nút bấm `[💬 Chat Zalo Ngay]`.
2. **Xây dựng Web Dashboard Local (FastAPI + Streamlit/HTML)**:
   - Giao diện tra cứu & lọc Lead trực tiếp trên trình duyệt local.
3. **Network Request Interception cho GraphQL Payload**:
   - Lắng nghe trực tiếp API response để lấy `publish_time` timestamp chuẩn 100%.
