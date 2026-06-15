"""Tests persistance état UI Menu & Drive."""

from app.services.drive_ui_state import migrate_row_states_by_platform


def test_migrate_row_states_by_platform_legacy():
    data = {
        "row_states": {
            "lait::L": {
                "url": "https://fd4-courses.leclercdrive.fr/fiche-produits-1.aspx",
                "contenance": 1.0,
                "unite": "L",
                "actif": True,
            }
        }
    }
    migrated = migrate_row_states_by_platform(data)
    assert "leclerc" in migrated
    assert migrated["leclerc"]["lait::L"]["url"].endswith("fiche-produits-1.aspx")
    assert "chronodrive" not in migrated


def test_migrate_row_states_by_platform_multi_store():
    data = {
        "row_states_by_platform": {
            "leclerc": {"oeufs::u": {"url": "https://leclercdrive.fr/x", "actif": True}},
            "chronodrive": {
                "oeufs::u": {"url": "https://www.chronodrive.com/oeufs-P1", "actif": True}
            },
        }
    }
    migrated = migrate_row_states_by_platform(data)
    assert migrated["leclerc"]["oeufs::u"]["url"] != migrated["chronodrive"]["oeufs::u"]["url"]
