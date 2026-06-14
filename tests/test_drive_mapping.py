"""Tests mapping Drive multi-enseigne."""

from app.services import drive_mapping_service as svc


def test_mapping_round_trip_multi_store(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)

    svc.save_mapping_entry(
        "lait entier",
        platform="leclerc",
        product_name="Lait UHT",
        product_url="https://www.leclercdrive.fr/produit/123#plus",
        product_id="123",
        contenance_paquet=1.0,
        unite_paquet="L",
    )
    entry = svc.get_store_mapping("Lait Entier", "leclerc")
    assert entry is not None
    assert entry["product_id"] == "123"
    assert entry["product_url"] == "https://www.leclercdrive.fr/produit/123"
    assert entry["contenance_paquet"] == 1.0
    assert entry["unite_paquet"] == "L"

    svc.save_mapping_entry(
        "lait entier",
        platform="chronodrive",
        product_name="Lait Chronodrive",
        product_url="https://www.chronodrive.com/auchan--lait-entier-P456",
        contenance_paquet=1.0,
        unite_paquet="L",
    )
    leclerc = svc.get_store_mapping("lait entier", "leclerc")
    chronodrive = svc.get_store_mapping("lait entier", "chronodrive")
    assert leclerc is not None and chronodrive is not None
    assert leclerc["product_url"] != chronodrive["product_url"]

    svc.remove_entry("lait entier", platform="leclerc")
    assert svc.get_store_mapping("lait entier", "leclerc") is None
    assert svc.get_store_mapping("lait entier", "chronodrive") is not None

    svc.remove_entry("lait entier")
    assert svc.get_store_mapping("lait entier", "chronodrive") is None


def test_legacy_flat_mapping_migrated(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    path.write_text(
        '{"epinards": {"product_name": "Epinards", "product_url": "https://x", "contenance_paquet": 600, "unite_paquet": "g"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)
    entry = svc.get_store_mapping("epinards", "leclerc")
    assert entry is not None
    assert entry["contenance_paquet"] == 600


def test_load_mapping_empty_file(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)
    assert svc.load_mapping() == {}


def test_load_mapping_invalid_json(tmp_path, monkeypatch):
    path = tmp_path / "drive_mapping.json"
    path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(svc, "DRIVE_MAPPING_PATH", path)
    assert svc.load_mapping() == {}


def test_chronodrive_product_fiche_detection():
    assert svc.is_chronodrive_product_fiche(
        "https://www.chronodrive.com/auchan--brocolis-fleurette-P481866"
    )
    assert not svc.is_chronodrive_product_fiche("https://www.chronodrive.com/")
    assert not svc.is_chronodrive_product_fiche(
        "https://www.chronodrive.com/magasins-chronodrive/drive-magasin-1061-portet-sur-garonne"
    )


def test_extract_chronodrive_product_id():
    assert (
        svc.extract_product_id(
            "https://www.chronodrive.com/sodebo--lovale---pizza-jambon-et-fromages-P139248"
        )
        == "139248"
    )
