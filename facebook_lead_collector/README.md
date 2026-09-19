# Facebook Lead Collector (Tìm Kiếm Lead Gia Sư Facebook)

Hệ thống tự động thu thập thông tin các bài đăng tìm kiếm gia sư từ các nguồn Facebook được phép truy cập, lọc từ khóa thông minh, lưu trữ SQLite và đồng bộ dữ liệu vào Google Sheets.

---

## Mục Lục

1. [Tổng Quan Kiến Trúc](#1-tổng-quan-kiến-trúc)
2. [Cấu Trúc Thư Mục](#2-cấu-trúc-thư-mục)
3. [Yêu Cầu Hệ Thống](#3-yêu-cầu-hệ-thống)
4. [Hướng Dẫn Cài Đặt Chi Tiết](#4-hướng-dẫn-cài-đặt-chi-tiết)
   - [Bước 1: Clone Project & Di chuyển vào thư mục](#bước-1-clone-project)
   - [Bước 2: Tạo Virtual Environment](#bước-2-tạo-virtual-environment)
   - [Bước 3: Kích hoạt Virtual Environment](#bước-3-kích-hoạt-virtual-environment)
   - [Bước 4: Cài đặt Dependencies](#bước-4-cài-đặt-dependencies)
   - [Bước 5: Cấu hình biến môi trường (.env)](#bước-5-cấu-hình-biến-môi-trường-env)
   - [Bước 6: Cấu hình Google Service Account & Google Sheets](#bước-6-cấu-hình-google-service-account)
   - [Bước 7: Khởi tạo Database SQLite](#bước-7-khởi-tạo-database-sqlite)
5. [Chế Độ Mock Mode (Không cần Token)](#5-chế-độ-mock-mode-không-cần-token)
6. [Cấu Hình Facebook API Hợp Lệ](#6-cấu-hình-facebook-api-hợp-lệ)
7. [Chạy Production & Chạy Định Kỳ](#7-chạy-production--chạy-định-kỳ)
8. [Kiểm Thử (Pytest)](#8-kiểm-thử-pytest)
9. [Xử Lý Lỗi & Giới Hạn Quan Trọng](#9-xử-lý-lỗi--giới-hạn-quan-trọng)

---

## 1. Tổng Quan Kiến Trúc

Quy trình xử lý dữ liệu (Pipeline):

```text
[Collector: Mock / Facebook Graph API]
                  │
                  ▼
          [Danh sách bài đăng]
                  │
                  ▼
         [Chuẩn hóa văn bản]
                  │
                  ▼
        [Keyword Filtering] ──(Không khớp)──► [Bỏ qua]
                  │
                (Khớp)
                  ▼
     [Kiểm tra trùng URL SQLite] ──(Đã tồn tại)──► [Đánh dấu Duplicate & Bỏ qua]
                  │
              (Chưa có)
                  ▼
         [Khởi tạo Model Lead]
                  │
                  ▼
       [Lưu vào SQLite (leads.db)]
                  │
                  ▼
   [Đồng bộ vào Google Sheets (nếu bật)]
```

---

## 2. Cấu Trúc Thư Mục

```text
facebook_lead_collector/
│
├── main.py                     # Entrypoint & CLI (--mock, --source, --schedule, ...)
├── config.py                   # Quản lý cấu hình tập trung (Pydantic / python-dotenv)
├── requirements.txt            # Danh sách thư viện phụ thuộc
├── README.md                   # Tài liệu hướng dẫn sử dụng tiếng Việt
├── .env.example                # File mẫu cấu hình biến môi trường
├── .gitignore                  # Bỏ qua file nhạy cảm, cache và database
│
├── collectors/                 # Module thu thập dữ liệu
│   ├── __init__.py
│   ├── base.py                 # Abstract BaseCollector
│   ├── facebook.py             # Facebook Graph API Collector
│   └── mock.py                 # MockFacebookCollector sinh dữ liệu giả lập
│
├── filters/                    # Module xử lý & lọc nội dung
│   ├── __init__.py
│   └── keyword_filter.py       # Bộ lọc từ khóa tiếng Việt không phân biệt hoa/thường
│
├── database/                   # Module cơ sở dữ liệu SQLite
│   ├── __init__.py
│   └── sqlite_db.py            # SQLite CRUD & deduplication theo post_url
│
├── sheets/                     # Module Google Sheets
│   ├── __init__.py
│   └── google_sheets.py        # Client Google Sheets (gspread + google-auth)
│
├── models/                     # Module Data Models (Pydantic)
│   ├── __init__.py
│   └── post.py                 # FacebookPost & Lead models
│
├── utils/                      # Module tiện ích
│   ├── __init__.py
│   ├── logger.py               # Custom Logger chuẩn format YYYY-MM-DD HH:MM:SS | LEVEL | MSG
│   └── text_utils.py           # Chuẩn hóa Unicode NFC & khoảng trắng
│
├── tests/                      # Bộ kiểm thử tự động
│   ├── __init__.py
│   ├── test_keyword_filter.py  # Unit test bộ lọc từ khóa
│   ├── test_database.py        # Unit test SQLite & deduplication
│   └── test_pipeline.py        # Integration test pipeline 5 bài (2 match, 1 dup, 2 no-match)
│
└── data/
    └── .gitkeep                # Thư mục chứa file SQLite leads.db
```

---

## 3. Yêu Cầu Hệ Thống

- **Python**: 3.10 trở lên (khuyên dùng Python 3.10 hoặc 3.11+).
- **Hệ điều hành**: Windows, macOS hoặc Linux.

---

## 4. Hướng Dẫn Cài Đặt Chi Tiết

### Bước 1: Clone Project

```bash
git clone <repository_url>
cd facebook_lead_collector
```

### Bước 2: Tạo Virtual Environment

```bash
python -m venv .venv
```

### Bước 3: Kích hoạt Virtual Environment

- Trên **Windows (PowerShell)**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- Trên **Windows (CMD)**:
  ```cmd
  .venv\Scripts\activate.bat
  ```
- Trên **Linux / macOS**:
  ```bash
  source .venv/bin/activate
  ```

### Bước 4: Cài đặt Dependencies

```bash
pip install -r requirements.txt
```

### Bước 5: Cấu hình biến môi trường (.env)

Sao chép file `.env.example` thành `.env`:

- Trên **Windows (PowerShell)**:
  ```powershell
  Copy-Item .env.example .env
  ```
- Trên **Linux / macOS / Git Bash**:
  ```bash
  cp .env.example .env
  ```

Nội dung `.env`:

```env
# Facebook API Configuration (Để trống nếu dùng chế độ Mock)
FACEBOOK_ACCESS_TOKEN=
FACEBOOK_API_BASE_URL=https://graph.facebook.com/v19.0
FACEBOOK_SOURCE_ID=

# Google Sheets Configuration (Service Account)
GOOGLE_CREDENTIALS_FILE=service_account.json
GOOGLE_SHEET_NAME=Facebook Leads
GOOGLE_WORKSHEET_NAME=Posts

# Database Configuration
DATABASE_PATH=data/leads.db

# Collector Configuration
COLLECTOR_LIMIT=100
LOG_LEVEL=INFO
```

### Bước 6: Cấu hình Google Service Account

Nếu muốn đồng bộ dữ liệu vào Google Sheets:

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/).
2. Tạo project mới (hoặc chọn project có sẵn).
3. Bật 2 API sau trong **APIs & Services > Enable APIs and Services**:
   - **Google Sheets API**
   - **Google Drive API**
4. Vào mục **IAM & Admin > Service Accounts** -> Nhấn **Create Service Account**.
5. Nhập tên tài khoản, sau đó nhấn **Done**.
6. Chọn Service Account vừa tạo, vào tab **Keys** > **Add Key** > **Create new key** > Chọn định dạng **JSON** > Tải file về.
7. Đổi tên file tải về thành `service_account.json` và đặt vào thư mục gốc của project (`facebook_lead_collector/service_account.json`).
8. Mở file `service_account.json`, tìm dòng `"client_email"` (ví dụ: `my-service-account@project-id.iam.gserviceaccount.com`).
9. Mở bảng tính Google Sheets bạn muốn ghi dữ liệu (đặt tên trùng với `GOOGLE_SHEET_NAME`, mặc định là `Facebook Leads`).
10. Nhấn nút **Share (Chia sẻ)** ở góc trên bên phải Google Sheets, dán địa chỉ `client_email` vào và cấp quyền **Editor (Người chỉnh sửa)**.

> *Lưu ý*: Nếu chưa có Google Service Account, hệ thống vẫn hoạt động bình thường ở chế độ Mock và tự động lưu dữ liệu vào SQLite.

### Bước 7: Khởi tạo Database SQLite

Chạy lệnh để tạo bảng lưu trữ `leads`:

```bash
python main.py --init-db
```

---

## 5. Chế Độ Mock Mode (Không Cần Token)

Chế độ Mock cho phép chạy thử nghiệm và kiểm chứng toàn bộ quy trình thu thập, lọc từ khóa, loại trừ trùng lặp và ghi dữ liệu mà **không cần** Facebook API Token hay Google Credentials:

```bash
python main.py --mock
```

Kết quả in ra console:

```text
2026-09-18 14:09:32 | INFO | Starting collector
2026-09-18 14:09:32 | INFO | Database initialized successfully at ...\data\leads.db
2026-09-18 14:09:32 | INFO | Database connection verified at: ...\data\leads.db
2026-09-18 14:09:32 | INFO | MockCollector starting simulation for source: 'default_source'
2026-09-18 14:09:32 | INFO | MockCollector generated 8 posts
2026-09-18 14:09:32 | INFO | Collected 8 posts
2026-09-18 14:09:32 | INFO | Found 6 matching posts
2026-09-18 14:09:32 | INFO | Added 5 new leads
2026-09-18 14:09:32 | INFO | Skipped 1 duplicate posts

Starting Facebook Lead Collector...

Collected: 8 posts
Keyword matched: 6
Duplicates: 1
New leads: 5

New leads:
1. Nguyễn Văn A | tìm gia sư, gia sư toán | https://facebook.com/groups/demo/posts/1001
2. Trần Thị B | cần gia sư, gia sư tiếng anh | https://facebook.com/groups/demo/posts/1002
3. Lê Văn C | cần giáo viên, gia sư lý | https://facebook.com/groups/demo/posts/1003
4. Vũ Minh F | tìm gia sư, gia sư hóa | https://facebook.com/groups/demo/posts/1007
5. Đặng Thu G | tìm gia sư, gia sư văn | https://facebook.com/groups/demo/posts/1008

Finished.
```

Nếu chạy lại lần thứ hai với cùng nguồn dữ liệu, hệ thống tự động nhận diện các URL đã có và không lưu duplicate:

```text
Collected: 8 posts
Keyword matched: 6
Duplicates: 6
New leads: 0
```

---

## 6. Cấu Hình Facebook API Hợp Lệ

Khi có quyền truy cập hợp lệ từ Meta for Developers:

1. Truy cập [Meta for Developers](https://developers.facebook.com/).
2. Tạo App hoặc sử dụng App có sẵn của tổ chức.
3. Yêu cầu cấp quyền đọc dữ liệu nhóm hoặc trang (ví dụ: `groups_access_member_info`, `pages_read_engagement`).
4. Lấy **User Access Token** hoặc **Page Access Token**.
5. Điền thông tin vào file `.env`:
   ```env
   FACEBOOK_ACCESS_TOKEN=EAAG...
   FACEBOOK_API_BASE_URL=https://graph.facebook.com/v19.0
   FACEBOOK_SOURCE_ID=your_group_id_here
   ```
6. Chạy với ID nhóm chỉ định:
   ```bash
   python main.py --source YOUR_GROUP_OR_PAGE_ID
   ```

---

## 7. Chạy Production & Chạy Định Kỳ

### 7.1. Chạy Đơn Lần

```bash
python main.py --source YOUR_GROUP_ID --limit 50
```

### 7.2. Chạy Định Kỳ Bằng Tham Số `--schedule` (Python Native)

Chạy pipeline tự động mỗi N phút (ví dụ: 15 phút):

```bash
python main.py --source YOUR_GROUP_ID --schedule 15
```

Hoặc chạy định kỳ với mock mode để kiểm tra:

```bash
python main.py --mock --schedule 5
```

### 7.3. Chạy Định Kỳ Bằng Windows Task Scheduler hoặc Linux Crontab

- **Linux Crontab** (chạy mỗi 30 phút):
  ```bash
  */30 * * * * cd /path/to/facebook_lead_collector && .venv/bin/python main.py --source YOUR_GROUP_ID >> logs/cron.log 2>&1
  ```
- **Windows Task Scheduler**: Tạo Basic Task gọi `C:\...\facebook_lead_collector\.venv\Scripts\python.exe` với đối số `main.py --source YOUR_GROUP_ID`.

---

## 8. Kiểm Thử (Pytest)

Toàn bộ các module đều có test suite đi kèm:

```bash
pytest
```

Chạy chi tiết:

```bash
pytest -v
```

Các kịch bản test bao gồm:
1. `tests/test_keyword_filter.py`:
   - Match từ khóa tiếng Việt có dấu, không dấu, khoảng trắng dư thừa, xuống dòng.
   - Nhận diện đúng chữ hoa ("CẦN GIA SƯ TOÁN").
   - Bỏ qua các bài đăng không liên quan ("Hôm nay trời đẹp").
   - Xử lý các bài viết có nhiều từ khóa cùng lúc ("Phụ huynh cần tìm gia sư toán lớp 8 tại Quận 7").
2. `tests/test_database.py`:
   - Tạo schema bảng SQLite.
   - Thêm lead mới, kiểm tra `lead_exists`.
   - Chặn tuyệt đối `post_url` trùng lặp (`UNIQUE` constraint).
   - Truy vấn toàn bộ danh sách lead.
3. `tests/test_pipeline.py`:
   - Chạy pipeline với 5 posts giả lập: 2 bài phù hợp, 1 bài trùng lặp URL, 2 bài không phù hợp -> Đảm bảo kết quả chính xác 2 new leads.
   - Chạy pipeline lần 2 với cùng dữ liệu -> 0 new leads, ghi nhận duplicate.

---

## 9. Xử Lý Lỗi & Giới Hạn Quan Trọng

### Tuân Thủ Chính Sách & Giới Hạn
- **KHÔNG** sử dụng tài khoản ảo để đăng nhập tự động.
- **KHÔNG** bypass CAPTCHA, Cloudflare, hay anti-bot của Facebook.
- **KHÔNG** cào trộm (scrape) bất hợp pháp.
- Dữ liệu thu thập phải thông qua Facebook Graph API chính thức hoặc nguồn dữ liệu mà người dùng được cấp quyền truy cập hợp lệ.

### Khả Năng Chịu Lỗi (Fault Tolerance)
- Một bài đăng bị lỗi cấu trúc dữ liệu hoặc URL rác sẽ được log lại và bỏ qua, **không** làm gián đoạn toàn bộ quá trình xử lý của các bài đăng khác.
- Khi mất kết nối Google Sheets hoặc chưa có file credentials, hệ thống sẽ log cảnh báo và tiếp tục lưu dữ liệu an toàn vào SQLite.
- Tự động cấu hình chuẩn `UTF-8` trên hệ điều hành Windows để hiển thị chính xác các ký tự tiếng Việt có dấu.
