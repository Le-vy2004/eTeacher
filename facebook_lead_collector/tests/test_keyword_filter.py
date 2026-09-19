"""Tests for keyword filtering functionality."""
import pytest
from filters.keyword_filter import find_matching_keywords


def test_tutor_request_matches_multiple_keywords():
    """Test text matching both 'tìm gia sư' and 'gia sư toán'."""
    text = "Phụ huynh cần tìm gia sư toán lớp 8 tại Quận 7."
    matches = find_matching_keywords(text)
    assert "tìm gia sư" in matches
    assert "gia sư toán" in matches


def test_grade_10_tutor_request_matches():
    """Test exact user test case: 'Tôi cần tìm gia sư toán lớp 10'."""
    text = "Tôi cần tìm gia sư toán lớp 10"
    matches = find_matching_keywords(text)
    assert "tìm gia sư" in matches
    assert "gia sư toán" in matches


def test_uppercase_matches():
    """Test uppercase input: 'CẦN GIA SƯ TOÁN'."""
    text = "CẦN GIA SƯ TOÁN"
    matches = find_matching_keywords(text)
    assert any("cần gia sư" in m.lower() for m in matches)
    assert any("gia sư toán" in m.lower() for m in matches)


def test_unrelated_text_returns_empty():
    """Test unrelated post: 'Hôm nay trời đẹp'."""
    text = "Hôm nay trời đẹp"
    matches = find_matching_keywords(text)
    assert matches == []


def test_redundant_whitespace_and_newlines():
    """Test text with irregular spaces, tabs, and newlines."""
    text = "\n\n  Cần   tìm   \t gia sư   tiếng Anh   \n cho bé lớp 3  "
    matches = find_matching_keywords(text)
    assert "tìm gia sư" in matches
    assert any("tiếng anh" in m.lower() for m in matches)


def test_empty_and_none_text():
    """Test edge cases with empty string or None."""
    assert find_matching_keywords("") == []
    assert find_matching_keywords(None) == []
    assert find_matching_keywords("   ") == []


def test_custom_keyword_list():
    """Test providing a custom list of keywords."""
    custom_keywords = ["gia sư đàn piano", "dạy bơi"]
    text = "Cần tìm gia sư đàn piano tại Hà Nội"
    matches = find_matching_keywords(text, custom_keywords)
    assert matches == ["gia sư đàn piano"]
