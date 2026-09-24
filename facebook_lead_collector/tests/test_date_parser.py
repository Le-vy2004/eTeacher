import sys
from pathlib import Path

project_dir = Path(__file__).resolve().parent.parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from datetime import datetime, timedelta
from utils.date_parser import is_within_days, parse_facebook_time


def test_parse_iso_time():
    iso = "2026-09-20T10:00:00+00:00"
    dt = parse_facebook_time(iso)
    assert dt.year == 2026
    assert dt.month == 9
    assert dt.day == 20


def test_parse_relative_vietnamese_time():
    ref = datetime(2026, 9, 22, 10, 0, 0)

    # Vừa xong
    assert (ref - parse_facebook_time("vừa xong", ref)).total_seconds() < 2

    # 3 giờ trước
    dt_3h = parse_facebook_time("3 giờ trước", ref)
    assert (ref - dt_3h).total_seconds() == 3 * 3600

    # 2 ngày trước
    dt_2d = parse_facebook_time("2 ngày", ref)
    assert (ref - dt_2d).days == 2

    # 3 tuần trước
    dt_3w = parse_facebook_time("3 tuần trước", ref)
    assert (ref - dt_3w).days == 21

    # 2 tháng trước
    dt_2m = parse_facebook_time("2 tháng", ref)
    assert (ref - dt_2m).days >= 59


def test_is_within_30_days():
    ref = datetime(2026, 9, 22, 10, 0, 0)

    recent_post = ref - timedelta(days=10)
    assert is_within_days(recent_post, days=30, reference_time=ref) is True

    boundary_post = ref - timedelta(days=29)
    assert is_within_days(boundary_post, days=30, reference_time=ref) is True

    old_post = ref - timedelta(days=45)
    assert is_within_days(old_post, days=30, reference_time=ref) is False

    two_months_ago = parse_facebook_time("2 tháng trước", ref)
    assert is_within_days(two_months_ago, days=30, reference_time=ref) is False


def test_is_within_hours():
    from utils.date_parser import is_within_hours, is_within_time_window
    ref = datetime(2026, 9, 24, 14, 0, 0)

    # 1 hour ago
    p_1h = parse_facebook_time("1 giờ trước", ref)
    assert is_within_hours(p_1h, hours=3, reference_time=ref) is True

    # 2 hours ago
    p_2h = parse_facebook_time("2 giờ trước", ref)
    assert is_within_hours(p_2h, hours=3, reference_time=ref) is True

    # 2.5 hours ago
    p_2_5h = ref - timedelta(hours=2, minutes=30)
    assert is_within_hours(p_2_5h, hours=3, reference_time=ref) is True

    # 4 hours ago (OUT OF WINDOW)
    p_4h = parse_facebook_time("4 giờ trước", ref)
    assert is_within_hours(p_4h, hours=3, reference_time=ref) is False

    # 20 hours ago (OUT OF WINDOW)
    p_20h = parse_facebook_time("20 giờ trước", ref)
    assert is_within_hours(p_20h, hours=3, reference_time=ref) is False

    # 1 day ago (OUT OF WINDOW)
    p_1d = parse_facebook_time("1 ngày", ref)
    assert is_within_time_window(p_1d, hours=3, reference_time=ref) is False

