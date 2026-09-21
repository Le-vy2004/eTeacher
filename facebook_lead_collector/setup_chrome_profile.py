"""
Script khởi tạo và đăng nhập Profile Chrome chuẩn trong dự án eTeacher.
Profile được lưu tại: facebook_lead_collector/profiles/chrome_profile/Default
"""
import os
import sys
from pathlib import Path

project_dir = Path(__file__).resolve().parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

# Auto-detect & inject project virtualenv (.venv) if global python is used
try:
    import dotenv
except ImportError:
    venv_sites = list(project_dir.glob(".venv/lib/python*/site-packages"))
    if venv_sites:
        sys.path.insert(0, str(venv_sites[0]))

from config import get_settings
from utils.logger import logger

def setup_project_chrome_profile():
    settings = get_settings()
    profile_dir = settings.resolved_chrome_user_data_path
    profile_name = settings.chrome_profile_name

    target_profile_path = profile_dir / profile_name
    target_profile_path.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🛠️ KHỞI TẠO DỰNG CHUẨN CHROME PROFILE TRONG DỰ ÁN eTeacher")
    print("=" * 70)
    logger.info(f"📁 Thư mục User Data : {profile_dir}")
    logger.info(f"👤 Thư mục Profile   : {target_profile_path}")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        logger.error("❌ Chưa cài đặt selenium. Vui lòng cài đặt bằng: .venv/bin/pip install -r requirements.txt")
        return

    logger.info("\n🌐 Đang mở trình duyệt Chrome chuẩn của dự án...")
    logger.info("👉 Vui lòng kiểm tra và đăng nhập tài khoản Facebook trên cửa sổ Chrome mở ra.")
    logger.info("⏳ Đăng nhập xong, Session/Cookies sẽ tự động lưu vĩnh viễn vào dự án!")

    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--profile-directory={profile_name}")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://www.facebook.com")

        print("\n" + "-" * 70)
        print("💡 CỬA SỔ CHROME DỰ ÁN ĐÃ MỞ:")
        print("1. Nếu đã vào Newsfeed ➔ Bạn có thể đóng trình duyệt.")
        print("2. Nếu chưa đăng nhập ➔ Đăng nhập tài khoản 1 lần duy nhất.")
        print("3. Nhấn ENTER tại màn hình console này khi hoàn tất để kết thúc.")
        print("-" * 70 + "\n")

        input(">>> Nhấn ENTER sau khi đã hoàn tất thao tác trên Chrome... ")

        driver.quit()
        logger.info("\n🎉 THIẾT LẬP CHROME PROFILE CHUẨN THÀNH CÔNG!")
        logger.info(f"✅ Về sau khi chạy: 'python main.py --source selenium', hệ thống sẽ tự động dùng Profile tại: {profile_dir}")

    except Exception as e:
        logger.error(f"💥 Lỗi khi khởi chạy Chrome Driver: {e}")
        logger.info("💡 Mẹo: Bạn cũng có thể copy một profile Chrome/Chromium có sẵn vào thư mục trên.")

if __name__ == "__main__":
    setup_project_chrome_profile()
