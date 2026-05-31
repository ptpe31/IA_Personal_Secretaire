"""Tests mapping Leclerc Drive."""

from app.services import drive_mapping_service as svc


def test_mapping_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)

    svc.save_mapping_entry(
        "lait entier",
        product_name="Lait UHT",
        product_url="https://www.leclercdrive.fr/produit/123",
        product_id="123",
    )
    entry = svc.get_mapping("Lait Entier")
    assert entry is not None
    assert entry["product_id"] == "123"

    svc.remove_entry("lait entier")
    assert svc.get_mapping("lait entier") is None


def test_load_mapping_empty_file(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)
    assert svc.load_mapping() == {}


def test_load_mapping_invalid_json(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)
    assert svc.load_mapping() == {}
