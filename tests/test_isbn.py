"""Unit tests for ISBN validation, regex extraction, and conversion."""

from app.services.isbn import (
    clean_isbn,
    extract_isbns_from_text,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    validate_and_sanitize_isbns,
)


def test_clean_isbn():
    assert clean_isbn(" 978-0-471-95869-7 ") == "9780471958697"
    assert clean_isbn("0-471-95869-X") == "047195869X"


def test_isbn10_valid_and_invalid():
    assert is_valid_isbn10("0471958697") is True
    assert is_valid_isbn10("047195869X") is False
    assert is_valid_isbn10("12345") is False


def test_isbn13_valid_and_invalid():
    assert is_valid_isbn13("9780471958697") is True
    assert is_valid_isbn13("9780471958698") is False
    assert is_valid_isbn13("abc9780471958697") is False


def test_isbn10_to_isbn13_conversion():
    converted = isbn10_to_isbn13("0471958697")
    assert converted == "9780471958697"
    assert isbn10_to_isbn13("invalid") is None


def test_extract_isbns_from_text():
    sample_text = "ISBN 978-0-471-95869-7 or older ISBN 0-471-95869-7 in back cover"
    v10s, v13s = extract_isbns_from_text(sample_text)
    assert "0471958697" in v10s
    assert "9780471958697" in v13s


def test_validate_and_sanitize_isbns():
    v10, v13, warns = validate_and_sanitize_isbns("0471958697", None)
    assert v10 == "0471958697"
    assert v13 == "9780471958697"
    assert len(warns) == 0

    bad_v10, bad_v13, bad_warns = validate_and_sanitize_isbns("1234567890", "9999999999999")
    assert bad_v10 is None
    assert bad_v13 is None
    assert len(bad_warns) == 2
