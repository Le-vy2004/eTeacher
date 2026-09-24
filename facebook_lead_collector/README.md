# eTeacher - Facebook Lead Collector & Auto Friend Requester

Hệ thống tự động hóa toàn diện cho việc thu thập khách hàng tiềm năng (Leads) gia sư từ Facebook:
1. **Thu thập bài đăng (Lead Scraping)**: Quét bài viết tìm gia sư từ Nhóm/Trang hoặc tìm kiếm toàn cầu Facebook bằng Chrome Profile đã đăng nhập, trích xuất số điện thoại, link Zalo, môn học, lớp, ngân sách, phân loại nhu cầu và lọc bài viết trong vòng N ngày gần đây.
2. **Loại bỏ bình luận & bài gia sư tự chào mời**: Chỉ lấy nội dung bài đăng chính chủ, loại trừ các bình luận quảng cáo nhận lớp.
3. **Tự động gửi lời mời kết bạn (Auto Friend Requester)**: Tự động lọc bỏ các tài khoản ẩn danh, truy cập trang cá nhân của tác giả bài đăng, kiểm tra trạng thái và nhấp nút "Thêm bạn bè" với cơ chế chống checkpoint Facebook.
4. **Đồng bộ Google Sheets & SQLite**: Tự động ghi nhận thông tin và cập nhật trạng thái kết bạn theo thời gian thực.

---

## 🚀 QUY TRÌNH SETUP & ĐĂNG NHẬP LẦN ĐẦU

### 📌 Bước 1: Khởi tạo môi trường Python
Mở Terminal / PowerShell tại thư mục `facebook_lead_collector`:

- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

- **Linux / macOS**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

---

### 📌 Bước 2: Setup Profile Chrome (Đăng nhập tài khoản Facebook)
Chạy công cụ tạo Profile Chrome độc lập của dự án:
```bash
python setup_chrome_profile.py
```
1. Cửa sổ trình duyệt Chrome riêng biệt sẽ mở ra.
2. Bạn tiến hành đăng nhập tài khoản Facebook trên cửa sổ Chrome vừa hiện.
3. Sau khi đăng nhập thành công và thấy Bảng tin Facebook (Newsfeed), quay lại màn hình Terminal / PowerShell và **nhấn phím ENTER**.
4. Phiên đăng nhập sẽ được lưu trữ an toàn trong `profiles/chrome_profile` (không lo bị mất session hay phải đăng nhập lại).

---

### 📌 Bước 3: Cấu hình nguồn dữ liệu & Google Sheets
1. **Google Sheets**: Đặt file chứng thực `service_account.json` vào thư mục `facebook_lead_collector/`. Bảng tính Google Sheet mặc định là `eTeacher` (tab `Posts`).
2. **Danh sách Nhóm/Trang**: Mở file `data/sources.txt` (hoặc tạo file riêng như `data/test_5_group.txt`) và dán các đường dẫn Facebook Group/Page cần thu thập (mỗi dòng 1 URL):
   ```txt
   https://www.facebook.com/groups/711749030995107/
   https://www.facebook.com/groups/giasudaytoan/
   https://www.facebook.com/groups/280811807457314/
   ```

---

## 📖 HƯỚNG DẪN SỬ DỤNG CÁC TÍNH NĂNG

### 1️⃣ Thu Thập Dữ Liệu Bài Đăng (Lead Scraping)

- **Quét toàn bộ danh sách trong `data/sources.txt`**:
  ```bash
  python main.py
  ```

- **Quét theo file nguồn tùy chọn & lọc bài đăng trong vòng 30 ngày**:
  ```bash
  python main.py --source-file data/test_5_group.txt --days 30 --scrolls 10 --limit 30
  ```

- **Tìm kiếm toàn cầu trên toàn Facebook (Global Search theo từ khóa)**:
  ```bash
  # Quét tự động theo bộ từ khóa tìm gia sư cốt lõi trên toàn Facebook
  python main.py --global-search --days 30

  # Quét toàn cầu với từ khóa tùy chỉnh
  python main.py --global-search --keyword "cần tìm gia sư toán hà nội" --days 15
  ```

- **Chạy định kỳ tự động lặp lại sau mỗi N phút**:
  ```bash
  python main.py --schedule 30
  ```

---

### 2️⃣ Tự Động Gửi Lời Mời Kết Bạn (Auto Friend Requester) 🤝

Hệ thống đọc dữ liệu cột **"🔗 Link Bài FB"** và **"Tên Người Đăng"** từ Google Sheet / SQLite để tự động kết bạn với phụ huynh/học sinh có nhu cầu:

- **Chạy gửi kết bạn (mặc định 15 tài khoản/lần)**:
  ```bash
  python main.py --add-friends
  ```

- **Chạy với số lượng tùy chỉnh (ví dụ: 10 tài khoản)**:
  ```bash
  python main.py --add-friends --friend-limit 10
  ```

- **Tùy chỉnh thời gian nghỉ an toàn chống Checkpoint Facebook**:
  ```bash
  # Nghỉ ngẫu nhiên 20s - 35s giữa các lần gửi
  python main.py --add-friends --friend-limit 15 --min-delay 20 --max-delay 35
  ```

#### 🛡️ Cơ chế xử lý an toàn & thông minh:
* **Bỏ qua tài khoản ẩn danh**: Tự động nhận diện thành viên ẩn danh trong nhóm Facebook (tên dạng `ElegantGoose3365`, `DecisiveWolf5241`, *Người tham gia ẩn danh*, v.v.) và gắn nhãn `Tài khoản ẩn danh (Bỏ qua)` trên Google Sheet mà không tốn thời gian mở trình duyệt.
* **Kiểm tra trạng thái kết bạn chính xác**: Phân biệt chuẩn xác nút `Thêm bạn bè` trên profile với các menu phụ hoặc danh sách bạn bè chung.
* **Tránh gửi trùng lặp**: Nhận diện nếu `Đã là bạn bè` hoặc `Đã gửi trước đó`.
* **Cập nhật thời gian thực**: Cập nhật kết quả vào cột **"Trạng Thái Kết Bạn"** (Cột N) và **"Thời Gian Kết Bạn"** (Cột O) trên Google Sheet.

---

## 📊 CẤU TRÚC DỮ LIỆU GOOGLE SHEETS (15 CỘT)

| Cột | Tên Cột | Mô Tả |
| :---: | :--- | :--- |
| **A** | `💬 Chat Zalo Direct` | Nút bấm hyperlink mở ngay khung chat Zalo với số điện thoại |
| **B** | `Số Điện Thoại` | Số điện thoại 10 số đã chuẩn hóa |
| **C** | `Môn Học` | Môn học cần gia sư (Toán, Tiếng Anh, Lý, Hóa, v.v.) |
| **D** | `Khối Lớp` | Khối lớp học sinh (Lớp 1 - 12, Đại học, Người đi làm) |
| **E** | `Ngân Sách (VND)` | Mức học phí hoặc "Thỏa thuận" |
| **F** | `🔗 Link Bài FB` | Hyperlink mở trực tiếp bài viết gốc |
| **G** | `Tên Người Đăng` | Tên tác giả bài viết |
| **H** | `Thời Gian Đăng` | Thời gian bài được đăng trên Facebook |
| **I** | `Nội Dung Bài Đăng` | Trích xuất riêng nội dung status gốc (loại trừ comment) |
| **J** | `Nhóm Facebook` | Nhóm/Trang nguồn |
| **K** | `Từ Khóa` | Các từ khóa tìm gia sư khớp |
| **L** | `Thời Gian Thu Thập` | Thời gian hệ thống thu thập lead |
| **M** | `Phân Loại` | Phụ huynh / Học sinh (tự động loại bỏ gia sư nhận lớp) |
| **N** | `Trạng Thái Kết Bạn` | `Đã gửi kết bạn`, `Tài khoản ẩn danh (Bỏ qua)`, `Đã là bạn bè`, v.v. |
| **O** | `Thời Gian Kết Bạn` | Thời gian gửi lời mời kết bạn |

---

## 📂 CẤU TRÚC THƯ MỤC DỰ ÁN

```text
facebook_lead_collector/
├── main.py                     # Entrypoint chính chạy cào lead & tự động kết bạn
├── setup_chrome_profile.py     # Khởi tạo & đăng nhập Chrome Profile lần đầu
├── config.py                   # Quản lý cấu hình (Pydantic / dotenv)
├── requirements.txt            # Danh sách thư viện Python
├── service_account.json        # File khóa kết nối Google Sheets API
├── README.md                   # Hướng dẫn chi tiết setup & sử dụng
├── .env                        # Biến môi trường hệ thống
│
├── actions/                    # Module hành động tương tác Facebook
│   └── friend_requester.py     # Tự động gửi kết bạn & lọc tài khoản ẩn danh
│
├── collectors/                 # Module cào dữ liệu Facebook Selenium
│   ├── base.py
│   ├── selenium_facebook.py    # Xử lý trích xuất bài viết & loại bỏ bình luận
│   └── group_discoverer.py     # Khám phá thêm nhóm gia sư mới
│
├── database/                   # Cơ sở dữ liệu SQLite
│   └── sqlite_db.py            # Lưu trữ leads & sources, chống trùng lặp
│
├── filters/                    # Bộ lọc dữ liệu thông minh
│   ├── keyword_filter.py       # Lọc từ khóa nhu cầu & loại trừ gia sư chào mời
│   └── cleaner.py              # Trích xuất SĐT, Zalo, môn học, khối lớp, ngân sách
│
├── models/                     # Data models (Pydantic)
│   └── post.py                 # FacebookPost & Lead data schema
│
├── sheets/                     # Tích hợp Google Sheets
│   └── google_sheets.py        # Đọc/ghi và cập nhật trạng thái kết bạn
│
├── utils/                      # Tiện ích bổ trợ
│   ├── date_parser.py          # Xử lý ngày giờ Facebook (vừa xong, N giờ, ngày/tháng)
│   ├── text_utils.py           # Chuẩn hóa văn bản tiếng Việt & số điện thoại
│   └── logger.py               # Hệ thống log màu Terminal
│
├── data/
│   ├── sources.txt             # Danh sách URL Nhóm/Trang Facebook cần quét
│   └── leads.db                # Database SQLite lưu trữ dữ liệu
│
└── profiles/
    └── chrome_profile/         # Lưu Profile Chrome & Session đăng nhập Facebook
```
