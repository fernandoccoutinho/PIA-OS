from fastapi import FastAPI

from app.api.documentation import ConsistencyReport, check_endpoint_documentation


def test_real_app_has_clean_documentation():
    from main import app as real_app

    report = check_endpoint_documentation(real_app)
    assert report.is_clean, report.render()


def test_report_render_when_clean():
    report = ConsistencyReport()
    assert "nenhum problema" in report.render()


def test_report_render_when_dirty():
    report = ConsistencyReport(endpoints_without_summary=["['GET'] /x"])
    assert "['GET'] /x" in report.render()
    assert report.is_clean is False


def test_detects_endpoint_missing_summary_and_tags():
    app = FastAPI()

    @app.get("/no-docs")
    def _no_docs():
        return {"ok": True}

    report = check_endpoint_documentation(app)
    assert any("/no-docs" in e for e in report.endpoints_without_summary)
    assert any("/no-docs" in e for e in report.endpoints_without_tags)
    assert any("/no-docs" in e for e in report.endpoints_without_description)


def test_detects_unknown_tag():
    app = FastAPI()

    @app.get("/x", tags=["NotInCatalog"], summary="x", description="x", responses={500: {}})
    def _x():
        return {"ok": True}

    report = check_endpoint_documentation(app)
    assert any("NotInCatalog" in e for e in report.endpoints_with_unknown_tags)


def test_well_documented_endpoint_produces_no_findings():
    app = FastAPI()

    @app.get(
        "/well-documented",
        tags=["Health"],
        summary="ok",
        description="descrição completa",
        responses={500: {"description": "erro"}},
    )
    def _ok():
        return {"ok": True}

    report = check_endpoint_documentation(app)
    assert report.is_clean
