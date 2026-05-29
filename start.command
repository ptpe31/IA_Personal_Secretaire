#!/bin/bash
# Lance Trankil-v2 depuis le dépôt (double-clic ou Terminal)
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

# Arrête une instance déjà lancée sur le port 8080
if lsof -ti :8080 >/dev/null 2>&1; then
  echo "Arrêt de l'instance Trankil-v2 existante (port 8080)…"
  lsof -ti :8080 | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# Logs détaillés : TRANKIL_LOG_LEVEL=DEBUG ./start.command
export TRANKIL_LOG_LEVEL="${TRANKIL_LOG_LEVEL:-INFO}"
echo "Niveau de logs : ${TRANKIL_LOG_LEVEL}"

exec .venv/bin/python main.py
