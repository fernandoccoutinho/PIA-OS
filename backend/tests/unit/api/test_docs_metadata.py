from datetime import datetime

from app.config.settings import Settings
from app.docs.metadata import build_api_metadata


def test_metadata_contains_all_expected_keys():
    metadata = build_api_metadata(Settings())
    assert set(metadata.keys()) == {
        "api_version",
        "backend_version",
        "pia_os_version",
        "generated_at",
    }


def test_metadata_reflects_settings_backend_version():
    metadata = build_api_metadata(Settings(app_version="9.9.9"))
    assert metadata["backend_version"] == "9.9.9"


def test_metadata_generated_at_is_valid_iso_timestamp():
    metadata = build_api_metadata(Settings())
    datetime.fromisoformat(metadata["generated_at"])  # não lança se for válido


def test_metadata_api_version_and_pia_os_version_are_non_empty():
    metadata = build_api_metadata(Settings())
    assert metadata["api_version"]
    assert metadata["pia_os_version"]
