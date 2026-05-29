#!/usr/bin/env python3
"""Initialise la base SQLite et l'arborescence Trankil-v2."""

from app.config import DB_PATH, ROOT_PATH, initialize_app_data


def main() -> None:
    initialize_app_data()
    print(f"✓ Dossiers créés sous {ROOT_PATH}")
    print(f"✓ Base SQLite : {DB_PATH}")


if __name__ == "__main__":
    main()
