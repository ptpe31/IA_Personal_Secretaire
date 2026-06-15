#!/bin/bash
# Lance IA-Secretaire depuis le dépôt (double-clic ou Terminal)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Création de l'environnement virtuel…"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -e .
else
  source .venv/bin/activate
fi

# Arrête toutes les instances IA-Secretaire de ce dépôt (évite 8080 + 8081 + 8082…)
MAIN_PATTERN="${SCRIPT_DIR}/.venv/bin/python -B main.py"
if pgrep -f "${MAIN_PATTERN}" >/dev/null 2>&1; then
  echo "Arrêt des instances IA-Secretaire existantes…"
  pkill -f "${MAIN_PATTERN}" 2>/dev/null || true
  sleep 1
fi
# Libère aussi le port par défaut au cas où un autre processus l'occupe
if lsof -ti :8080 >/dev/null 2>&1; then
  echo "Libération du port 8080…"
  lsof -ti :8080 | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# Logs détaillés : TRANKIL_LOG_LEVEL=DEBUG ./start.command
export TRANKIL_LOG_LEVEL="${TRANKIL_LOG_LEVEL:-INFO}"
echo "Niveau de logs : ${TRANKIL_LOG_LEVEL}"

# WeasyPrint — bibliothèques Homebrew Apple Silicon / Intel
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

# Évite les imports obsolètes après une mise à jour du code
find "$SCRIPT_DIR/app" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

exec .venv/bin/python -B main.py
