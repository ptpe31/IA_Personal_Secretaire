"""Tests ingestion Inbox."""

from app.services.inbox_ingest import build_paste_filename, is_paste_mime_allowed


def test_paste_mime_allowed():
    assert is_paste_mime_allowed("image/png")
    assert is_paste_mime_allowed("image/jpeg")
    assert not is_paste_mime_allowed("text/plain")


def test_build_paste_filename():
    name = build_paste_filename("image/png")
    assert name.startswith("paste_")
    assert name.endswith(".png")
