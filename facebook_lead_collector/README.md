# Facebook Lead Collector - Hướng Dẫn Setup & Sử Dụng

Hệ thống tự động thu thập thông tin bài đăng tìm kiếm gia sư từ các Nhóm/Trang Facebook bằng Chrome Profile đã đăng nhập, tự động lọc từ khóa nhu cầu gia sư thực sự và lưu trữ dữ liệu vào SQLite (`data/leads.db`) cũng như đồng bộ Google Sheets.

---

## 🚀 QÙY TRÌNH HƯỚNG DẪN SETUP & CHẠY HỆ THỐNG

### TRƯỜNG HỢP 1: MÁY ĐÃ SETUP MÔI TRƯỜNG PYTHON (Máy Công Ty) ⭐ [ƯU TIÊN]

> Trên các máy đã có sẵn môi trường Python và dependencies (hoặc thư mục `.venv` trong dự án), hệ thống đã được tích hợp cơ chế tự động nhận diện Virtual Environment, bạn **không cần kích hoạt thủ công**.

#### 📌 Bước 1: Setup Profile Chrome (Đăng nhập tài khoản lần đầu)
Chạy script khởi tạo Profile Chrome độc lập của dự án:
```bash
python setup_chrome_profile.py
```
1. Cửa sổ trình duyệt Chrome riêng biệt sẽ mở ra.
2. Bạn tiến hành đăng nhập tài khoản Facebook trên cửa sổ Chrome vừa hiện.
3. Sau khi đăng nhập thành công và thấy trang tin Facebook (Newsfeed), quay lại màn hình Terminal / CMD / PowerShell và **nhấn phím ENTER**.
4. Phiên đăng nhập sẽ được lưu trữ an toàn trong thư mục `profiles/chrome_profile` (file này đã được bảo vệ trong `.gitignore` không lo bị lộ).

#### 📌 Bước 2: Cấu hình danh sách Nhóm / Trang Facebook cần quét
Mở file `data/sources.txt` và dán các đường dẫn Facebook Group/Page cần thu thập dữ liệu (mỗi dòng 1 URL):
```txt
https://www.facebook.com/groups/711749030995107/
https://www.facebook.com/groups/giasudaytoan/
https://www.facebook.com/groups/280811807457314/
```

#### 📌 Bước 3: Lệnh chạy cào dữ liệu (Raw Data)
- **Chạy quét 1 lần**:
  ```bash
  python main.py
  ```
- **Chạy quét định kỳ tự động** (ví dụ lặp lại sau mỗi 30 phút):
  ```bash
  python main.py --schedule 30
  ```

---

### TRƯỜNG HỢP 2: MÁY MỚI CHƯA SETUP MÔI TRƯỜNG PYTHON (Máy Cá Nhân / Máy Mới)

> Dành cho máy lần đầu tải dự án về và chưa có môi trường Python Virtualenv.

#### 📌 Bước 1: Khởi tạo môi trường Virtualenv & Cài đặt thư viện
Mở Terminal / PowerShell tại thư mục dự án `facebook_lead_collector`:

- **Trên Linux / macOS**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

- **Trên Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

- **Trên Windows (CMD)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  pip install -r requirements.txt
  ```

#### 📌 Bước 2: Setup Profile Chrome lần đầu
```bash
python setup_chrome_profile.py
```
*(Thực hiện đăng nhập Facebook trên cửa sổ Chrome mở ra, sau đó bấm ENTER tại terminal để lưu session)*.

#### 📌 Bước 3: Lệnh chạy thu thập dữ liệu
- **Cách 1: Chạy khi đã active môi trường ảo**:
  ```bash
  python main.py
  ```
- **Cách 2: Gọi trực tiếp python trong môi trường ảo (không cần active)**:
  - Trên **Windows**:
    ```powershell
    .\.venv\Scripts\python main.py
    ```
  - Trên **Linux / macOS**:
    ```bash
    .venv/bin/python main.py
    ```
- **Chạy lặp lại định kỳ N phút/lần**:
  ```bash
  python main.py --schedule 15
  ```

---

## 📂 Cấu Trúc Thư Mục Dự Án Tối Giản

```text
facebook_lead_collector/
├── main.py                     # Entrypoint chính chạy cào dữ liệu & batch sources
├── setup_chrome_profile.py     # Tool khởi tạo & đăng nhập Chrome Profile lần đầu
├── config.py                   # Cấu hình hệ thống (Pydantic / dotenv)
├── requirements.txt            # Danh sách thư viện Python
├── README.md                   # Tài liệu hướng dẫn cài đặt & sử dụng
├── .env.example                # File mẫu biến môi trường
├── .gitignore                  # Cấu hình bỏ qua file cá nhân/phiên làm việc
│
├── collectors/                 # Module cào dữ liệu Selenium Facebook
│   ├── base.py
│   └── selenium_facebook.py
│
├── database/                   # Module lưu trữ dữ liệu SQLite
│   └── sqlite_db.py            # Bảng leads & sources, tự động lọc trùng URL
│
├── filters/                    # Module lọc từ khóa nhu cầu gia sư
│   └── keyword_filter.py
│
├── models/                     # Data models (Pydantic)
│   └── post.py
│
├── sheets/                     # Đồng bộ Google Sheets
│   └── google_sheets.py
│
├── data/
│   ├── sources.txt             # File dán danh sách URL Nhóm/Trang Facebook
│   └── leads.db                # Cơ sở dữ liệu SQLite lưu Lead thu thập được
│
└── profiles/
    └── chrome_profile/         # Nơi lưu Profile Chrome & Session Facebook cá nhân
```
