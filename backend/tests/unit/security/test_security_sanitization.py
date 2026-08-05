from app.security.sanitization import (
    mask_sensitive_value,
    normalize_unicode,
    remove_control_characters,
    sanitize_string,
)


def test_remove_control_characters_strips_null_byte():
    assert remove_control_characters("abc\x00def") == "abcdef"


def test_remove_control_characters_keeps_common_whitespace():
    value = "linha1\nlinha2\tfim\r"
    assert remove_control_characters(value) == value


def test_remove_control_characters_strips_other_control_chars():
    assert remove_control_characters("a\x01\x02b") == "ab"


def test_normalize_unicode_reduces_to_canonical_form():
    # 'é' como caractere único vs 'e' + acento combinante -> mesma forma NFKC
    combined = "e\u0301"
    single = "é"
    assert normalize_unicode(combined) == normalize_unicode(single)


def test_sanitize_string_strips_and_cleans():
    assert sanitize_string("  ol\x00á  ") == "olá"


def test_mask_sensitive_value_keeps_last_chars_visible():
    assert mask_sensitive_value("supersecret123", visible_chars=4) == "**********t123"


def test_mask_sensitive_value_short_value_fully_masked():
    assert mask_sensitive_value("abc", visible_chars=4) == "***"


def test_mask_sensitive_value_default_visible_chars():
    masked = mask_sensitive_value("0123456789")
    assert masked.endswith("6789")
    assert masked.count("*") == 6
