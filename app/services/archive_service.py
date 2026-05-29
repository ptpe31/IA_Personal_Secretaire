"""Recherche et exploration GED — spec §7."""

from __future__ import annotations

from datetime import date

from app import config
from app.db.connection import get_connection
from app.models.archive import ArchiveItem


def matches_search_query(
    *,
    query: str,
    title: str,
    raw_summary: str | None,
    stored_path: str | None,
    original_filename: str | None,
    tags: list[str],
) -> bool:
    """Vérifie si un document correspond à la requête full-text."""
    needle = query.strip().lower()
    if not needle:
        return True

    haystacks = [
        title,
        raw_summary or "",
        stored_path or "",
        original_filename or "",
        " ".join(tags),
    ]
    return any(needle in value.lower() for value in haystacks)


def search_archives(
    *,
    query: str = "",
    category_filter: str = "all",
    tag_filters: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_desc: bool = True,
) -> list[ArchiveItem]:
    """
    Recherche dans les archives GED (spec §7.2).

    Full-text sur titre, raw_summary, nom fichier, tags.
    Filtres catégorie, tags (OR), plage dates émission.
    """
    sql = """
        SELECT
            t.id, t.title, t.category, t.date_emission, t.raw_summary,
            d.stored_path, d.original_filename,
            GROUP_CONCAT(tg.name, ',') AS tag_list
        FROM tasks t
        INNER JOIN documents d ON d.id = t.document_id
        LEFT JOIN task_tags tt ON tt.task_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE d.stored_path IS NOT NULL
    """
    params: list[object] = []

    if category_filter in ("pro", "perso"):
        sql += " AND t.category = ?"
        params.append(category_filter)

    if date_from is not None:
        sql += " AND t.date_emission >= ?"
        params.append(date_from.isoformat())

    if date_to is not None:
        sql += " AND t.date_emission <= ?"
        params.append(date_to.isoformat())

    order = "DESC" if sort_desc else "ASC"
    sql += f" GROUP BY t.id ORDER BY t.date_emission {order}, t.id {order}"

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    tag_filters_set = {t.lower() for t in (tag_filters or []) if t}
    items: list[ArchiveItem] = []

    for row in rows:
        tags = [t.strip() for t in (row["tag_list"] or "").split(",") if t.strip()]

        if tag_filters_set:
            if not {t.lower() for t in tags}.intersection(tag_filters_set):
                continue

        title = str(row["title"])
        raw_summary = str(row["raw_summary"]) if row["raw_summary"] else None
        stored_path = str(row["stored_path"])
        original_filename = (
            str(row["original_filename"]) if row["original_filename"] else None
        )

        if not matches_search_query(
            query=query,
            title=title,
            raw_summary=raw_summary,
            stored_path=stored_path,
            original_filename=original_filename,
            tags=tags,
        ):
            continue

        absolute = config.ROOT_PATH / stored_path
        items.append(
            ArchiveItem(
                task_id=int(row["id"]),
                title=title,
                category=str(row["category"]),
                date_emission=date.fromisoformat(str(row["date_emission"])),
                stored_path=stored_path,
                absolute_path=absolute,
                file_exists=absolute.is_file(),
                original_filename=original_filename,
                raw_summary=raw_summary,
                tags=tags,
            )
        )

    return items
