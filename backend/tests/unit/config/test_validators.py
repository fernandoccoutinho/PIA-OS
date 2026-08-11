import pytest

from app.config.validators import (
    validate_database_url,
    validate_jwt_algorithm,
    validate_log_destination,
    validate_log_format,
    validate_log_level,
    validate_non_empty_name,
    validate_port,
)


def test_validate_port_accepts_valid_range():
    assert validate_port(5432) == 5432
    assert validate_port(1) == 1
    assert validate_port(65535) == 65535


def test_validate_port_rejects_out_of_range():
    with pytest.raises(ValueError):
        validate_port(0)
    with pytest.raises(ValueError):
        validate_port(70000)


def test_validate_log_level_normalizes_case():
    assert validate_log_level("info") == "INFO"
    assert validate_log_level("Debug") == "DEBUG"


def test_validate_log_level_rejects_unknown():
    with pytest.raises(ValueError):
        validate_log_level("VERBOSE")


def test_validate_log_format_normalizes_case():
    assert validate_log_format("JSON") == "json"


def test_validate_log_format_rejects_unknown():
    with pytest.raises(ValueError):
        validate_log_format("xml")


def test_validate_log_destination_accepts_single_value():
    assert validate_log_destination("console") == "console"


def test_validate_log_destination_accepts_comma_separated_list():
    assert validate_log_destination("console, file") == "console,file"


def test_validate_log_destination_normalizes_case():
    assert validate_log_destination("Console,FILE") == "console,file"


def test_validate_log_destination_rejects_unknown_value():
    with pytest.raises(ValueError):
        validate_log_destination("console,carrier-pigeon")


def test_validate_log_destination_rejects_empty():
    with pytest.raises(ValueError):
        validate_log_destination("")


def test_validate_jwt_algorithm_accepts_supported():
    assert validate_jwt_algorithm("hs256") == "HS256"


def test_validate_jwt_algorithm_rejects_unsupported():
    with pytest.raises(ValueError):
        validate_jwt_algorithm("RS256")


def test_validate_non_empty_name_strips_and_validates():
    assert validate_non_empty_name("  PIA-OS  ", field_name="APP_NAME") == "PIA-OS"
    with pytest.raises(ValueError):
        validate_non_empty_name("   ", field_name="APP_NAME")


def test_validate_database_url_accepts_postgresql():
    url = "postgresql+psycopg://user:pw@host:5432/db"
    assert validate_database_url(url) == url


def test_validate_database_url_rejects_non_postgres_scheme():
    with pytest.raises(ValueError):
        validate_database_url("mysql://user:pw@host:3306/db")


def test_validate_database_url_rejects_missing_host():
    with pytest.raises(ValueError):
        validate_database_url("postgresql://")
