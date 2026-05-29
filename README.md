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

### Raccourci Inbox — coller une capture

1. Capture d'écran (⌘⇧4) ou copie d'image depuis Mail
2. Onglet **Inbox** → cliquer la zone **Coller une capture**
3. **⌘V** — l'analyse démarre comme pour un glisser-déposer

Les PDF et fichiers restent en **glisser-déposer** (ou bouton Choisir).

## Structure données

```
~/Trankil-v2/
├── Pro/GED/
├── Perso/GED/
├── .inbox/
├── .credentials/google_calendar/
└── database.sqlite
```

## Google Calendar (optionnel)

1. Créez un projet sur [Google Cloud Console](https://console.cloud.google.com/).
2. Activez l'API **Google Calendar**.
3. Créez des identifiants **OAuth 2.0 — Application de bureau**.
4. Téléchargez le JSON et placez-le ici :

```
~/Trankil-v2/.credentials/google_calendar/credentials.json
```

5. Dans Trankil-v2 → **Paramètres** → **Connecter Google Calendar** (ouvre le navigateur OAuth).
6. Utilisez **Synchroniser l'agenda** sur une tâche, ou activez la sync auto dans Paramètres.

## Notifications

- Relances **J-3** et **J-1** via notifications macOS.
- Actives tant que l'application est ouverte (daemon `launchd` prévu en V1.1).
- Désactivables dans **Paramètres**.
