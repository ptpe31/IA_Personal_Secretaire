"""Tests parsing requêtes panier Leclerc."""

from app.services.leclerc_driver import _parse_cart_payload, is_product_page_valid


class _FakeRequest:
    def __init__(self, url: str, method: str = "POST", body: dict | None = None):
        self.url = url
        self.method = method
        self._body = body

    @property
    def post_data_json(self):
        return self._body


def test_parse_cart_payload_from_url_path():
    req = _FakeRequest("https://www.leclercdrive.fr/ajout/123456")
    result = _parse_cart_payload(req, "https://www.leclercdrive.fr/produit/123456")
    assert result["product_id"] == "123456"
    assert "product_url" in result


def test_parse_cart_payload_from_query():
    req = _FakeRequest("https://www.leclercdrive.fr/panier?productId=789")
    result = _parse_cart_payload(req, "https://example.com/p/789")
    assert result["product_id"] == "789"


def test_parse_cart_payload_from_body():
    req = _FakeRequest(
        "https://www.leclercdrive.fr/panier/add",
        body={"codeArticle": "555"},
    )
    result = _parse_cart_payload(req, "https://example.com/p/555")
    assert result["product_id"] == "555"


def test_is_product_page_valid():
    assert is_product_page_valid("https://x.fr/produit/123", "123") is True
    assert is_product_page_valid("https://x.fr/accueil", "123") is False
