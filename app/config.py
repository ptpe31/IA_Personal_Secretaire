"""Configuration globale et initialisation des dossiers Trankil-v2."""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Chemin racine fixe V1 (spec §3.3)
ROOT_PATH: Path = Path.home() / "Trankil-v2"

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

PRO_GED_PATH: Path = ROOT_PATH / "Pro" / "GED"
PERSO_GED_PATH: Path = ROOT_PATH / "Perso" / "GED"
INBOX_PATH: Path = ROOT_PATH / ".inbox"
DB_PATH: Path = ROOT_PATH / "database.sqlite"
CREDENTIALS_PATH: Path = ROOT_PATH / ".credentials" / "google_calendar"
DRIVE_MAPPING_PATH: Path = ROOT_PATH / "drive_mapping.json"
CURRENT_MENU_PATH: Path = ROOT_PATH / "current_menu.json"
LECLERC_PROFILE_PATH: Path = ROOT_PATH / ".leclerc_profile"

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
APP_PORT_FALLBACK_ATTEMPTS: int = 20
APP_TITLE: str = "IA-Secretaire"


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Vérifie si un port TCP est libre pour l'écoute."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def resolve_listen_port(
    preferred: int = APP_PORT,
    *,
    max_attempts: int = APP_PORT_FALLBACK_ATTEMPTS,
) -> int:
    """
    Retourne le port d'écoute NiceGUI.

    Priorité : TRANKIL_PORT / APP_PORT (env) → port préféré → ports suivants.
    """
    load_dotenv()
    env_port = os.environ.get("TRANKIL_PORT") or os.environ.get("APP_PORT")
    if env_port:
        port = int(env_port)
        if not is_port_available(port):
            raise OSError(
                f"Port {port} déjà utilisé (variable TRANKIL_PORT ou APP_PORT)."
            )
        return port

    for offset in range(max_attempts):
        port = preferred + offset
        if is_port_available(port):
            if offset:
                logger.warning(
                    "Port %d occupé — écoute sur http://localhost:%d",
                    preferred,
                    port,
                )
            return port

    raise OSError(
        f"Aucun port disponible entre {preferred} et {preferred + max_attempts - 1}."
    )

# Email SMTP (relances J-1) — surchargeables via ~/Trankil-v2/config.yaml et .env
DEFAULT_SMTP_SERVER: str = "smtp.gmail.com"
DEFAULT_SMTP_PORT: int = 587
USER_CONFIG_YAML: Path = ROOT_PATH / "config.yaml"

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


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool
    smtp_server: str
    smtp_port: int
    sender_email: str
    recipient_email: str
    app_password: str | None


def _parse_email_yaml_section(text: str) -> dict[str, str | int | bool]:
    """Parse minimal de la section `email:` dans config.yaml (sans dépendance PyYAML)."""
    data: dict[str, str | int | bool] = {}
    in_email = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "email:":
            in_email = True
            continue
        if not in_email:
            continue
        if line and not line[0].isspace():
            break
        if ":" not in stripped:
            continue
        key, _, raw_value = stripped.partition(":")
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key == "enabled":
            data[key] = value.lower() in ("true", "1", "yes", "on")
        elif key == "smtp_port":
            try:
                data[key] = int(value)
            except ValueError:
                data[key] = DEFAULT_SMTP_PORT
        elif value:
            data[key] = value
    return data


def _load_email_yaml_config() -> dict[str, str | int | bool]:
    for path in (USER_CONFIG_YAML, PROJECT_ROOT / "config.yaml"):
        if path.is_file():
            return _parse_email_yaml_section(path.read_text(encoding="utf-8"))
    return {}


def get_email_config() -> EmailConfig:
    """
    Configuration SMTP pour les relances email.

    Priorité : settings SQLite → config.yaml → .env → valeurs par défaut.
    Le mot de passe d'application Google doit être dans .env (SMTP_APP_PASSWORD).
    """
    load_dotenv()
    from app.db.connection import get_setting

    yaml_cfg = _load_email_yaml_config()

    def _bool_setting(key: str, yaml_key: str, default: bool = True) -> bool:
        stored = (get_setting(key) or "").strip().lower()
        if stored in ("true", "false"):
            return stored == "true"
        if yaml_key in yaml_cfg:
            return bool(yaml_cfg[yaml_key])
        return default

    def _str_setting(key: str, yaml_key: str, env_key: str = "", default: str = "") -> str:
        stored = (get_setting(key) or "").strip()
        if stored:
            return stored
        yaml_val = yaml_cfg.get(yaml_key)
        if isinstance(yaml_val, str) and yaml_val.strip():
            return yaml_val.strip()
        if env_key:
            env_val = os.environ.get(env_key, "").strip()
            if env_val:
                return env_val
        return default

    smtp_port_raw = (get_setting("smtp_port") or "").strip()
    if smtp_port_raw.isdigit():
        smtp_port = int(smtp_port_raw)
    elif isinstance(yaml_cfg.get("smtp_port"), int):
        smtp_port = int(yaml_cfg["smtp_port"])
    else:
        smtp_port = DEFAULT_SMTP_PORT

    sender = _str_setting("sender_email", "sender_email", "SMTP_SENDER_EMAIL")
    recipient = _str_setting("recipient_email", "recipient_email", "SMTP_RECIPIENT_EMAIL")
    if not recipient:
        recipient = sender

    app_password = os.environ.get("SMTP_APP_PASSWORD", "").strip()
    if not app_password:
        yaml_pwd = yaml_cfg.get("app_password")
        if isinstance(yaml_pwd, str) and yaml_pwd.strip():
            app_password = yaml_pwd.strip()

    return EmailConfig(
        enabled=_bool_setting("email_reminder_enabled", "enabled", default=True),
        smtp_server=_str_setting(
            "smtp_server",
            "smtp_server",
            default=DEFAULT_SMTP_SERVER,
        )
        or DEFAULT_SMTP_SERVER,
        smtp_port=smtp_port,
        sender_email=sender,
        recipient_email=recipient,
        app_password=app_password or None,
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
    load_dotenv()
    ensure_directories()
    from app.db.connection import init_db

    init_db()
