from app.docs.tags import (
    ACTIVE_TAG_NAMES,
    ALL_TAGS,
    PLACEHOLDER_TAG_NAMES,
    TAG_HEALTH,
    build_openapi_tags_metadata,
)


def test_all_tags_have_unique_names():
    names = [t.name for t in ALL_TAGS]
    assert len(names) == len(set(names))


def test_active_and_placeholder_partition_all_tags():
    assert {t.name for t in ALL_TAGS} == ACTIVE_TAG_NAMES | PLACEHOLDER_TAG_NAMES
    assert set() == ACTIVE_TAG_NAMES & PLACEHOLDER_TAG_NAMES


def test_placeholder_groups_exist_for_future_modules():
    for name in ("Administration", "Authentication", "Objects", "Sessions"):
        assert name in PLACEHOLDER_TAG_NAMES


def test_active_groups_match_existing_endpoints():
    for name in ("System", "Health", "Status", "Version", "Metrics"):
        assert name in ACTIVE_TAG_NAMES


def test_build_openapi_tags_metadata_format():
    metadata = build_openapi_tags_metadata()
    assert all({"name", "description"} <= set(entry.keys()) for entry in metadata)
    names = [entry["name"] for entry in metadata]
    assert TAG_HEALTH.name in names


def test_every_tag_has_a_non_empty_description():
    for tag in ALL_TAGS:
        assert tag.description.strip()
