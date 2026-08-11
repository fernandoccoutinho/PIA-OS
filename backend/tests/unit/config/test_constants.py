from app.config import constants


def test_app_identity_constants_are_non_empty():
    assert constants.APP_NAME
    assert constants.APP_VERSION
    assert constants.API_PREFIX.startswith("/api/")


def test_port_bounds_are_valid_tcp_range():
    assert constants.MIN_PORT == 1
    assert constants.MAX_PORT == 65535
    assert constants.MIN_PORT < constants.DEFAULT_DB_PORT < constants.MAX_PORT


def test_valid_log_levels_cover_standard_levels():
    assert {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} == constants.VALID_LOG_LEVELS


def test_valid_log_formats():
    assert frozenset({"json", "text"}) == constants.VALID_LOG_FORMATS


def test_default_jwt_algorithm_is_in_valid_set():
    assert constants.DEFAULT_JWT_ALGORITHM in constants.VALID_JWT_ALGORITHMS


def test_pagination_limits_are_sane():
    assert 0 < constants.DEFAULT_PAGE_SIZE <= constants.MAX_PAGE_SIZE
