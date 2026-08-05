from app.config.settings import Settings
from app.security.cors import build_cors_kwargs


def test_build_cors_kwargs_defaults():
    kwargs = build_cors_kwargs(Settings())
    assert kwargs["allow_origins"] == ["*"]
    assert "GET" in kwargs["allow_methods"]
    assert kwargs["allow_headers"] == ["*"]
    assert kwargs["allow_credentials"] is False


def test_build_cors_kwargs_custom_origins():
    settings = Settings(cors_allowed_origins="https://a.com,https://b.com")
    kwargs = build_cors_kwargs(settings)
    assert kwargs["allow_origins"] == ["https://a.com", "https://b.com"]


def test_build_cors_kwargs_with_credentials():
    settings = Settings(
        cors_allowed_origins="https://trusted.example.com", cors_allow_credentials=True
    )
    kwargs = build_cors_kwargs(settings)
    assert kwargs["allow_credentials"] is True
    assert kwargs["allow_origins"] == ["https://trusted.example.com"]
