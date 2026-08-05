from fastapi import FastAPI

from app.config.settings import Settings
from app.docs.openapi import apply_metadata_extension, build_openapi_kwargs, build_servers


def test_build_openapi_kwargs_has_required_keys():
    kwargs = build_openapi_kwargs(Settings())
    for key in (
        "title",
        "description",
        "version",
        "openapi_tags",
        "servers",
        "contact",
        "license_info",
    ):
        assert key in kwargs


def test_build_openapi_kwargs_title_matches_settings():
    settings = Settings(app_name="Meu Backend")
    kwargs = build_openapi_kwargs(settings)
    assert kwargs["title"] == "Meu Backend"


def test_build_openapi_kwargs_description_includes_changelog():
    kwargs = build_openapi_kwargs(Settings())
    assert "Changelog" in kwargs["description"]


def test_build_servers_reflects_environment():
    servers = build_servers(Settings(environment="production"))
    assert "production" in servers[0]["description"]


def test_apply_metadata_extension_injects_x_metadata():
    settings = Settings()
    app = FastAPI(**build_openapi_kwargs(settings))
    apply_metadata_extension(app, settings)

    schema = app.openapi()
    assert "x-metadata" in schema["info"]
    assert schema["info"]["x-metadata"]["backend_version"] == settings.app_version


def test_apply_metadata_extension_is_valid_openapi_3_1():
    settings = Settings()
    app = FastAPI(**build_openapi_kwargs(settings))
    apply_metadata_extension(app, settings)
    schema = app.openapi()
    assert schema["openapi"].startswith("3.1")
