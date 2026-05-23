from feme.db import Database
from feme.source_registry import SourceRegistry, _changed_rows


class _Cursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


def test_changed_rows_handles_none_negative_and_positive():
    assert _changed_rows(_Cursor(None)) == 0
    assert _changed_rows(_Cursor(-1)) == 0
    assert _changed_rows(_Cursor(0)) == 0
    assert _changed_rows(_Cursor(1)) == 1
    assert _changed_rows(_Cursor(5)) == 5


def test_source_registry_does_not_require_total_changes(tmp_path):
    db = Database(tmp_path / "test.sqlite")
    db.init()
    registry = SourceRegistry(db)
    registry.upsert(
        "user_note",
        project_id="p1",
        enabled=True,
        review_required=False,
        default_quality=0.5,
    )
    rule = registry.assert_enabled("user_note", project_id="p1")
    assert bool(rule["enabled"]) is True
