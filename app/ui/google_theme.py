"""Thème visuel Google Workspace — classes et helpers NiceGUI / Quasar."""

from __future__ import annotations

from datetime import datetime

GOOGLE_CSS = """
body, .nicegui-content {
    background-color: #f9fafb !important;
}
.trankil-page {
    background-color: #f9fafb;
}
.trankil-header {
    background: #ffffff !important;
    color: #202124 !important;
    border-bottom: 1px solid #e5e7eb;
    box-shadow: none !important;
}
.trankil-nav-tabs .q-tab {
    border-radius: 9999px;
    margin-right: 6px;
    padding: 8px 20px;
    min-height: 40px;
    color: #5f6368;
    font-weight: 500;
    text-transform: none;
}
.trankil-nav-tabs .q-tab--active {
    background: #e8f0fe !important;
    color: #1a73e8 !important;
}
.trankil-nav-tabs .q-tab__indicator {
    display: none;
}
.trankil-chip {
    border-radius: 9999px;
    border: 1px solid #dadce0;
    padding: 4px 16px;
    font-size: 0.8125rem;
    font-weight: 500;
    text-transform: none;
    min-height: 32px;
    color: #3c4043;
    background: #ffffff;
    transition: all 0.15s ease;
}
.trankil-chip:hover {
    background: #f1f3f4;
}
.trankil-chip-active-all {
    background: #202124 !important;
    color: #ffffff !important;
    border-color: transparent !important;
}
.trankil-chip-active-pro {
    background: #e8f0fe !important;
    color: #1967d2 !important;
    border-color: #aecbfa !important;
}
.trankil-chip-active-perso {
    background: #e6f4ea !important;
    color: #137333 !important;
    border-color: #ceead6 !important;
}
.trankil-task-card {
    border-radius: 16px;
    transition: box-shadow 0.2s ease;
}
.trankil-task-card:hover {
    box-shadow: 0 4px 12px rgba(60, 64, 67, 0.12);
}
.trankil-task-card-urgent {
    border-left: 4px solid #ea4335;
}
.trankil-expansion {
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    overflow: hidden;
}
.trankil-icon-btn {
    color: #9aa0a6 !important;
}
.trankil-icon-btn:hover {
    color: #5f6368 !important;
}
.trankil-icon-btn-danger:hover {
    color: #ea4335 !important;
}
.trankil-date-pill {
    background: #f1f3f4;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 0.75rem;
    color: #3c4043;
}
.trankil-card-actions {
    border-top: 1px solid #e5e7eb;
    padding-top: 8px;
    margin-top: 12px;
}
.trankil-view-toggle {
    border-radius: 9999px;
    border: 1px solid #dadce0;
    background: #ffffff;
    color: #5f6368;
    min-height: 32px;
    min-width: 36px;
}
.trankil-view-toggle-active {
    background: #e8f0fe !important;
    color: #1967d2 !important;
    border-color: #aecbfa !important;
}
.trankil-list-row {
    transition: background-color 0.15s ease;
}
.trankil-list-batch {
    transition: box-shadow 0.15s ease;
}
.trankil-list-batch:hover {
    box-shadow: 0 2px 8px rgba(60, 64, 67, 0.08);
}
.trankil-omnibox-wrap {
    background: #ffffff;
    border: 1px solid #dadce0;
    border-radius: 9999px;
    padding: 0 12px 0 10px;
    min-height: 36px;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.trankil-omnibox-wrap:focus-within {
    border-color: #aecbfa;
    box-shadow: 0 0 0 1px #aecbfa;
}
.trankil-omnibox-wrap .q-field {
    flex: 1;
    min-width: 0;
}
.trankil-omnibox-wrap .q-field__control {
    min-height: 34px;
}
.trankil-omnibox-wrap .q-field__control:before,
.trankil-omnibox-wrap .q-field__control:after {
    display: none;
}
.trankil-omnibox-wrap input {
    font-size: 0.875rem;
    color: #3c4043;
}
.trankil-tag-suggestion {
    border-radius: 9999px;
    border: 1px solid #dadce0;
    padding: 2px 12px;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: none;
    min-height: 28px;
    color: #5f6368;
    background: #ffffff;
}
.trankil-tag-suggestion:hover {
    background: #e8f0fe;
    color: #1967d2;
    border-color: #aecbfa;
}
"""

# Quasar utility bundles + Tailwind (NiceGUI tailwind=True)
PAGE_BG = "trankil-page"

# Pastel Google Keep — une couleur par lot document (document_id % 6)
BATCH_PASTEL_PALETTE: tuple[str, ...] = (
    "bg-blue-50/40 border-blue-100",      # 0 — Bleu doux
    "bg-amber-50/50 border-amber-100",    # 1 — Jaune Keep
    "bg-purple-50/40 border-purple-100",  # 2 — Lilas
    "bg-teal-50/40 border-teal-100",      # 3 — Menthe
    "bg-rose-50/40 border-rose-100",      # 4 — Rose poudré
    "bg-orange-50/40 border-orange-100",  # 5 — Abricot
)

BATCH_BORDER_LEFT: tuple[str, ...] = (
    "border-l-4 border-blue-400",
    "border-l-4 border-amber-400",
    "border-l-4 border-purple-400",
    "border-l-4 border-teal-400",
    "border-l-4 border-rose-400",
    "border-l-4 border-orange-400",
)

CARD_SHELL = (
    "trankil-task-card w-full q-mb-sm q-pa-md rounded-2xl border shadow-sm "
    "hover:shadow-md transition-shadow duration-200"
)
CARD_GOOGLE = f"{CARD_SHELL} bg-white border-gray-200"
EXPANSION_GOOGLE = "trankil-expansion w-full q-mb-md"
BADGE_PRO = "bg-blue-1 text-blue-9 text-xs font-medium rounded-full q-px-sm q-py-xs"
BADGE_PERSO = "bg-green-1 text-green-9 text-xs font-medium rounded-full q-px-sm q-py-xs"
BADGE_RECURRENCE = "bg-purple-1 text-purple-9 text-xs rounded-full q-px-sm q-py-xs"
SUGGESTION_BOX = (
    "bg-white/80 border border-gray-200/50 text-grey-9 q-pa-sm rounded-borders text-sm"
)
COLUMN_URGENT_BADGE = "bg-red-1 text-red-9 text-xs rounded-full q-px-sm q-py-xs"
COLUMN_TODO_BADGE = "bg-blue-1 text-blue-9 text-xs rounded-full q-px-sm q-py-xs"
COLUMN_ARCHIVED_BADGE = "bg-green-1 text-green-9 text-xs rounded-full q-px-sm q-py-xs"
ICON_MUTED = "text-grey-5"
ICON_BTN = "trankil-icon-btn"
ICON_BTN_DANGER = "trankil-icon-btn trankil-icon-btn-danger"

FILTER_CHIP_BASE = "trankil-chip"
FILTER_CHIP_ACTIVE = {
    "all": "trankil-chip trankil-chip-active-all",
    "pro": "trankil-chip trankil-chip-active-pro",
    "perso": "trankil-chip trankil-chip-active-perso",
}


def apply_google_theme() -> None:
    """Injecte les styles globaux Google Workspace."""
    from nicegui import ui

    ui.add_css(GOOGLE_CSS)


def chip_classes(category_key: str, active_key: str) -> str:
    if category_key == active_key:
        return FILTER_CHIP_ACTIVE.get(category_key, FILTER_CHIP_BASE)
    return FILTER_CHIP_BASE


def category_badge_classes(category: str) -> str:
    return BADGE_PRO if category == "pro" else BADGE_PERSO


def batch_color_index(
    document_id: int | None,
    created_at: datetime | None = None,
) -> int | None:
    """Index palette 0–5 : lot document ou création manuelle (même seconde)."""
    if document_id is not None:
        return document_id % len(BATCH_PASTEL_PALETTE)
    if created_at is not None:
        stamp = int(created_at.replace(microsecond=0).strftime("%Y%m%d%H%M%S"))
        return stamp % len(BATCH_PASTEL_PALETTE)
    return None


def task_card_classes(
    *,
    document_id: int | None,
    created_at: datetime | None = None,
    urgent: bool = False,
) -> str:
    """Classes carte Kanban : fond pastel partagé par lot (document ou création)."""
    color_idx = batch_color_index(document_id, created_at)
    if color_idx is None:
        classes = f"{CARD_SHELL} bg-white border-gray-200"
    else:
        classes = f"{CARD_SHELL} {BATCH_PASTEL_PALETTE[color_idx]}"
    if urgent:
        classes += " trankil-task-card-urgent"
    return classes


def batch_border_left_classes(
    document_id: int | None,
    created_at: datetime | None = None,
) -> str:
    """Bordure gauche colorée par lot — vue Liste."""
    color_idx = batch_color_index(document_id, created_at)
    if color_idx is None:
        return "border-l-4 border-gray-200"
    return BATCH_BORDER_LEFT[color_idx]


def view_toggle_classes(active: bool) -> str:
    base = "trankil-view-toggle"
    return f"{base} trankil-view-toggle-active" if active else base


def render_date_meta(*, icon: str, value: str, label: str = "") -> None:
    """Ligne métadonnée avec icône Material et pilule grise."""
    from nicegui import ui

    with ui.row().classes("items-center q-gutter-xs q-mb-xs"):
        ui.icon(icon, size="xs").classes(ICON_MUTED)
        if label:
            ui.label(label).classes("text-caption text-grey-6")
        ui.label(value).classes("trankil-date-pill")
