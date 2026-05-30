#!/usr/bin/env python3
"""
Sauvegarde automatisée de ~/Trankil-v2/database.sqlite vers Google Drive.

Étapes : snapshot SQLite cohérent → gzip → chiffrement GPG symétrique → rclone copy → rotation 7 jours.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "backup.log"

DEFAULT_DB_PATH = Path.home() / "Trankil-v2" / "database.sqlite"
DEFAULT_RCLONE_REMOTE = "gdrive"
DEFAULT_RCLONE_PATH = "Trankil-Backups"
RETENTION_DAYS = 7


class BackupStepError(Exception):
    """Erreur sur une étape nommée du pipeline de sauvegarde."""

    def __init__(self, step: str, message: str) -> None:
        self.step = step
        super().__init__(message)


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _resolve_db_path() -> Path:
    raw = os.environ.get("DB_PATH", "").strip()
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return DEFAULT_DB_PATH.resolve()


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("backup_db")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def _require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        brew_pkg = "gnupg" if name == "gpg" else name
        raise BackupStepError(
            name,
            f"Commande introuvable : {name}. Installez-la via Homebrew (brew install {brew_pkg}).",
        )
    return path


def _run_command(step: str, cmd: list[str], *, input_text: str | None = None) -> None:
    try:
        subprocess.run(
            cmd,
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or f"code de sortie {exc.returncode}"
        raise BackupStepError(step, details) from exc


def _snapshot_database(source: Path, destination: Path) -> None:
    """Copie cohérente via sqlite3.backup() (compatible WAL, sans bloquer l'app)."""
    source_uri = f"file:{source}?mode=ro"
    src_conn = sqlite3.connect(source_uri, uri=True)
    try:
        dest_conn = sqlite3.connect(destination)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def _compress_gzip(source: Path, destination: Path) -> None:
    with source.open("rb") as src, gzip.open(destination, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)


def _encrypt_gpg_symmetric(source: Path, destination: Path, passphrase: str) -> None:
    _require_command("gpg")
    _run_command(
        "gpg",
        [
            "gpg",
            "--batch",
            "--yes",
            "--symmetric",
            "--cipher-algo",
            "AES256",
            "--passphrase-fd",
            "0",
            "-o",
            str(destination),
            str(source),
        ],
        input_text=passphrase,
    )


def _upload_rclone(local_file: Path, remote: str, remote_path: str) -> None:
    _require_command("rclone")
    target = f"{remote}:{remote_path}/"
    _run_command("rclone", ["rclone", "copy", str(local_file), target, "--stats-one-line"])


def _rotate_old_backups(remote: str, remote_path: str) -> None:
    target = f"{remote}:{remote_path}/"
    _run_command(
        "rclone",
        [
            "rclone",
            "delete",
            target,
            "--min-age",
            f"{RETENTION_DAYS}d",
            "--stats-one-line",
        ],
    )


def run_backup() -> None:
    logger = _setup_logging()
    _load_dotenv()

    db_path = _resolve_db_path()
    passphrase = os.environ.get("BACKUP_GPG_PASSPHRASE", "").strip()
    remote = os.environ.get("RCLONE_REMOTE", DEFAULT_RCLONE_REMOTE).strip() or DEFAULT_RCLONE_REMOTE
    remote_path = os.environ.get("RCLONE_BACKUP_PATH", DEFAULT_RCLONE_PATH).strip() or DEFAULT_RCLONE_PATH

    if not passphrase:
        raise BackupStepError(
            "config",
            "BACKUP_GPG_PASSPHRASE manquante dans .env",
        )

    if not db_path.is_file():
        raise BackupStepError(
            "config",
            f"Base SQLite introuvable : {db_path}",
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"database-{timestamp}.sqlite"

    logger.info("=== Début sauvegarde %s ===", backup_name)
    logger.info("Source : %s | Remote : %s:%s", db_path, remote, remote_path)

    with tempfile.TemporaryDirectory(prefix="trankil-backup-") as tmp_dir:
        tmp = Path(tmp_dir)
        snapshot_path = tmp / backup_name
        gz_path = tmp / f"{backup_name}.gz"
        gpg_path = tmp / f"{backup_name}.gz.gpg"

        logger.info("[1/5] Snapshot SQLite (sqlite3.backup)")
        try:
            _snapshot_database(db_path, snapshot_path)
        except sqlite3.Error as exc:
            raise BackupStepError("snapshot", str(exc)) from exc
        logger.info("[1/5] Snapshot OK (%d octets)", snapshot_path.stat().st_size)

        logger.info("[2/5] Compression gzip")
        try:
            _compress_gzip(snapshot_path, gz_path)
        except OSError as exc:
            raise BackupStepError("gzip", str(exc)) from exc
        logger.info("[2/5] Compression OK (%d octets)", gz_path.stat().st_size)

        logger.info("[3/5] Chiffrement GPG symétrique (AES256)")
        _encrypt_gpg_symmetric(gz_path, gpg_path, passphrase)
        logger.info("[3/5] Chiffrement OK (%d octets)", gpg_path.stat().st_size)

        logger.info("[4/5] Transfert rclone vers %s:%s/", remote, remote_path)
        _upload_rclone(gpg_path, remote, remote_path)
        logger.info("[4/5] Transfert OK")

        logger.info("[5/5] Rotation (suppression > %d jours)", RETENTION_DAYS)
        _rotate_old_backups(remote, remote_path)
        logger.info("[5/5] Rotation OK")

    logger.info("=== Sauvegarde terminée avec succès ===")


def main() -> int:
    logger = _setup_logging()
    try:
        run_backup()
        return 0
    except BackupStepError as exc:
        logger.error("Échec à l'étape [%s] : %s", exc.step, exc)
        return 1
    except Exception as exc:
        logger.exception("Échec inattendu : %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
