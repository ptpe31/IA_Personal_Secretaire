"""Configuration globale et initialisation des dossiers Trankil-v2."""

from __future__ import annotations

from pathlib import Path

# Chemin racine fixe V1 (spec §3.3)
ROOT_PATH: Path = Path.home() / "Trankil-v2"

PRO_GED_PATH: Path = ROOT_PATH / "Pro" / "GED"
PERSO_GED_PATH: Path = ROOT_PATH / "Perso" / "GED"
INBOX_PATH: Path = ROOT_PATH / ".inbox"
DB_PATH: Path = ROOT_PATH / "database.sqlite"
CREDENTIALS_PATH: Path = ROOT_PATH / ".credentials" / "google_calendar"

REQUIRED_DIRECTORIES: tuple[Path, ...] = (
    PRO_GED_PATH,
    PERSO_GED_PATH,
    INBOX_PATH,
    CREDENTIALS_PATH,
)

# Ollama (spec §9.1)
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str = "llama3.2-vision"
OLLAMA_TIMEOUT_SECONDS: int = 120

# NiceGUI
APP_PORT: int = 8080
APP_TITLE: str = "Trankil-v2"

# Extensions acceptées par l'Inbox (spec §5.1)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic"}
)


def ensure_directories() -> None:
    """Crée l'arborescence ~/Trankil-v2 si elle n'existe pas."""
    for directory in REQUIRED_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def ged_path_for_category(category: str) -> Path:
    """Retourne le dossier GED correspondant à la catégorie."""
    if category == "perso":
        return PERSO_GED_PATH
    return PRO_GED_PATH


def initialize_app_data() -> None:
    """Point d'entrée unique : dossiers + base SQLite."""
    ensure_directories()
    from app.db.connection import init_db

    init_db()
