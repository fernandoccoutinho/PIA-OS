from app.docs.changelog import API_CHANGELOG, render_changelog_markdown


def test_changelog_has_entries():
    assert len(API_CHANGELOG) > 0


def test_every_entry_has_version_module_and_changes():
    for entry in API_CHANGELOG:
        assert entry.version
        assert entry.module
        assert len(entry.changes) > 0


def test_render_changelog_markdown_includes_all_modules():
    markdown = render_changelog_markdown()
    for entry in API_CHANGELOG:
        assert entry.module in markdown


def test_render_changelog_markdown_starts_with_title():
    markdown = render_changelog_markdown()
    assert markdown.startswith("# Changelog da API")


def test_render_changelog_markdown_includes_bullet_points():
    markdown = render_changelog_markdown()
    assert "- " in markdown
