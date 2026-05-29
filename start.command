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

python main.py
