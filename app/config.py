"""Configuration globale et initialisation des dossiers Trankil-v2."""

from __future__ import annotations

import os
from pathlib import Path

# Chemin racine fixe V1 (spec §3.3)
ROOT_PATH: Path = Path.home() / "Trankil-v2"

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

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

# Ollama (fallback local)
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str = "llama3.2-vision"
OLLAMA_TIMEOUT_SECONDS: int = 120

# Google Gemini (analyse documentaire — modèle fixe)
GEMINI_MODEL: str = "gemini-2.5-flash"

# OpenRouter (mode Éco — Qwen vision)
OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL: str = "qwen/qwen-2.5-vl-72b-instruct"
OPENROUTER_TIMEOUT_SECONDS: int = 120
OPENROUTER_HTTP_REFERER: str = "https://github.com/lala/trankil-v2"

IA_PROVIDER_GEMINI: str = "Gemini (Natif)"
IA_PROVIDER_OPENROUTER: str = "OpenRouter (Éco)"
IA_PROVIDER_OPTIONS: tuple[str, ...] = (IA_PROVIDER_GEMINI, IA_PROVIDER_OPENROUTER)

# NiceGUI
APP_PORT: int = 8080
APP_TITLE: str = "Trankil-v2"

# Extensions acceptées par l'Inbox (spec §5.1)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic"}
)

_ENV_LOADED = False


def load_dotenv() -> None:
    """Charge les variables depuis .env à la racine du projet (sans écraser l'environnement)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_file = PROJECT_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    _ENV_LOADED = True


def get_gemini_api_key() -> str | None:
    """Clé API Gemini : variable d'environnement puis table settings."""
    load_dotenv()
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    from app.db.connection import get_setting

    for key in ("gemini_api_key", "GEMINI_API_KEY"):
        stored = get_setting(key)
        if stored and stored.strip():
            return stored.strip()
    return None


def get_gemini_model() -> str:
    """Modèle Gemini fixe (gemini-2.5-flash), surchargeable via GEMINI_MODEL (.env)."""
    load_dotenv()
    env_model = os.environ.get("GEMINI_MODEL", "").strip()
    return env_model or GEMINI_MODEL


def get_active_ia_provider() -> str:
    """Moteur IA principal : settings.active_ia_provider → Gemini par défaut."""
    from app.db.connection import get_setting

    stored = (get_setting("active_ia_provider") or "").strip()
    if stored in IA_PROVIDER_OPTIONS:
        return stored
    return IA_PROVIDER_GEMINI


def get_openrouter_api_key() -> str | None:
    """Clé OpenRouter : OPENROUTER_API_KEY (.env) puis settings."""
    load_dotenv()
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    from app.db.connection import get_setting

    stored = (get_setting("openrouter_api_key") or "").strip()
    return stored or None


def get_openrouter_model() -> str:
    """Modèle OpenRouter : settings → défaut Qwen VL."""
    from app.db.connection import get_setting

    stored = (get_setting("openrouter_model") or "").strip()
    return stored or OPENROUTER_DEFAULT_MODEL


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
    load_dotenv()
    ensure_directories()
    from app.db.connection import init_db

    init_db()
