# Trankil-v2

Assistant secrétaire **local-first** pour Mac.

## Prérequis

```bash
brew install poppler          # conversion PDF
brew install ollama           # IA locale
ollama pull llama3.2-vision
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Lancement

```bash
python scripts/init_db.py     # init dossiers + SQLite
python main.py                # http://localhost:8080
```

Ou double-clic sur `start.command`.

## Structure données

```
~/Trankil-v2/
├── Pro/GED/
├── Perso/GED/
├── .inbox/
└── database.sqlite
```
