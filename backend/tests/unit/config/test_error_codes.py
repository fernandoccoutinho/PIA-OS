from app.core.error_codes import (
    ALL_ERROR_CODES,
    ERROR_CODE_BY_CODE,
    PIA_1002_NOT_FOUND,
    PIA_1005_HTTP_ERROR,
    ErrorCategory,
    ErrorSeverity,
    error_code_for_http_status,
)


def test_all_codes_are_unique():
    codes = [ec.code for ec in ALL_ERROR_CODES]
    assert len(codes) == len(set(codes))


def test_all_codes_follow_pia_prefix_format():
    for ec in ALL_ERROR_CODES:
        assert ec.code.startswith("PIA-")
        assert ec.code[4:].isdigit()
        assert len(ec.code[4:]) == 4


def test_all_codes_have_valid_http_status():
    for ec in ALL_ERROR_CODES:
        assert 100 <= ec.http_status <= 599


def test_all_codes_have_valid_category_and_severity():
    for ec in ALL_ERROR_CODES:
        assert isinstance(ec.category, ErrorCategory)
        assert isinstance(ec.severity, ErrorSeverity)


def test_error_code_by_code_lookup():
    assert ERROR_CODE_BY_CODE["PIA-1002"] is PIA_1002_NOT_FOUND


def test_error_code_for_known_http_status():
    assert error_code_for_http_status(404) is PIA_1002_NOT_FOUND


def test_error_code_for_unknown_http_status_falls_back_to_generic():
    assert error_code_for_http_status(418) is PIA_1005_HTTP_ERROR


def test_error_category_ranges_are_distinct_number_prefixes():
    # PIA-0xxx=system, PIA-1xxx=api, PIA-2xxx=validation, PIA-3xxx=database,
    # PIA-4xxx=configuration, PIA-5xxx=infrastructure, PIA-6xxx=external,
    # PIA-7xxx=authentication — o primeiro dígito do número reflete a categoria.
    prefix_to_category = {
        "0": ErrorCategory.SYSTEM,
        "1": ErrorCategory.API,
        "2": ErrorCategory.VALIDATION,
        "3": ErrorCategory.DATABASE,
        "4": ErrorCategory.CONFIGURATION,
        "5": ErrorCategory.INFRASTRUCTURE,
        "6": ErrorCategory.EXTERNAL,
        "7": ErrorCategory.AUTHENTICATION,
    }
    for ec in ALL_ERROR_CODES:
        digits = ec.code.split("-")[1]
        assert ec.category == prefix_to_category[digits[0]]
