"""Tests palette pastel par lot document / création manuelle."""

from datetime import datetime

from app.ui.google_theme import (
    BATCH_PASTEL_PALETTE,
    batch_color_index,
    task_card_classes,
)


def test_batch_color_index_from_document_id():
    assert batch_color_index(12) == 0
    assert batch_color_index(13) == 1
    assert batch_color_index(None) is None


def test_same_document_same_palette_index():
    doc_id = 42
    assert batch_color_index(doc_id) == batch_color_index(doc_id)
    assert batch_color_index(doc_id) == doc_id % len(BATCH_PASTEL_PALETTE)


def test_manual_tasks_same_second_share_color():
    ts = datetime(2026, 5, 29, 16, 41, 22)
    assert batch_color_index(None, ts) == batch_color_index(None, ts)
    assert batch_color_index(None, ts) is not None


def test_manual_task_gets_pastel_not_white():
    ts = datetime(2026, 5, 29, 16, 41, 22)
    classes = task_card_classes(document_id=None, created_at=ts, urgent=False)
    assert "bg-white" not in classes
    idx = batch_color_index(None, ts)
    assert BATCH_PASTEL_PALETTE[idx] in classes


def test_document_task_gets_pastel_palette():
    classes = task_card_classes(document_id=3, urgent=False)
    assert BATCH_PASTEL_PALETTE[3] in classes


def test_urgent_keeps_left_border_marker():
    classes = task_card_classes(document_id=3, urgent=True)
    assert "trankil-task-card-urgent" in classes
