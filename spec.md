# Trankil-v2 — Spécification Technique & Fonctionnelle

> **Version** : 0.12-implemented  
> **Date** : 31 mai 2026  
> **Statut** : V1 fonctionnelle + **Menu & Drive** (planning batch cooking, robot Leclerc Playwright)  
> **Dépôt git** : `IA_Personal_Secretaire` · **Nom UI** : **Trankil-v2**

---

## Table des matières

1. [Vision & Principes](#1-vision--principes)
2. [Stack technique & contraintes](#2-stack-technique--contraintes)
3. [Architecture système](#3-architecture-système)
4. [Modèle de données](#4-modèle-de-données)
5. [Vue principale — Tableau de bord unifié](#5-vue-principale--tableau-de-bord-unifié)
6. [Vue secondaire — Inbox (validation manuelle)](#6-vue-secondaire--inbox-validation-manuelle)
7. [Vue 3 — GED / Archives](#7-vue-3--ged--archives)
8. [Vue 4 — Menu & Drive](#8-vue-4--menu--drive)
9. [Automatisations](#9-automatisations)
10. [Intégration IA — Gemini, OpenRouter, Ollama & mock](#10-intégration-ia--gemini-openrouter-ollama--mock)
11. [Intégration Google Calendar](#11-intégration-google-calendar)
12. [Arborescence projet](#12-arborescence-projet)
13. [Plan d'implémentation itérative](#13-plan-dimplémentation-itérative)
14. [Décisions validées (arbitrages Architecte)](#14-décisions-validées-arbitrages-architecte)
15. [Critères d'acceptation (MVP → V1)](#15-critères-dacceptation-mvp--v1)

---

## 1. Vision & Principes

### 1.1 Objectif produit

**Trankil-v2** est un assistant/secrétaire virtuel **local-first** pour Mac, destiné à un jeune entrepreneur. Il transforme courriers scannés, photos iPhone et captures d'écran en **tâches actionnables**, les organise dans un **tableau de bord Kanban**, archive les documents dans une **GED structurée**, et déclenche des **relances** et une **sync agenda** optionnelle.

Le dépôt de développement s'appelle `IA_Personal_Secretaire` ; l'application affichée et le dossier utilisateur portent le nom **Trankil-v2**.

### 1.2 Principes non négociables

| Principe | Description |
|----------|-------------|
| **Local-first (données)** | SQLite + filesystem local sous `~/Trankil-v2` ; pas de compte obligatoire. |
| **Analyse documentaire** | **Gemini** (natif) ou **OpenRouter / Qwen** (mode Éco) selon Paramètres ; sinon **Ollama** local ; sinon **mock** démo. |
| **Mac natif** | Notifications macOS, chemin fixe `~/Trankil-v2`. |
| **Itératif** | MVP testable sans IA (mode mock), enrichissement progressif. |
| **Français V1** | Interface en français uniquement ; pas d'i18n en V1. |

### 1.3 Persona & workflow quotidien (référence UX)

**Depuis V0.3** : le **Tableau de bord** est la page d'accueil (`/`). L'Inbox n'est plus un passage obligatoire.

```
[Courrier PDF] ──► Scanner ──┐
[Photo iPhone] ──► HEIC ────┤
[Mail capture] ──► PNG ─────┤──► Dashboard (dépôt) ──► Analyse IA ──► Kanban + GED
                             │         (OpenRouter → Gemini → Ollama → mock)
                             │                              │
                             │                              └─► (Autopilote OFF ou erreur)
                             │                                       └─► Inbox (validation manuelle)
                             └─► Coller ⌘V dans zone dédiée
```

| Mode | Comportement |
|------|--------------|
| **Autopilote ON** (défaut) | Document analysé → tâches créées automatiquement → fichier archivé en GED → l'utilisateur reste sur le Dashboard. |
| **Autopilote OFF** ou **erreur analyse IA** | Document mis en file Inbox → bannière cliquable sur le Dashboard : « N document(s) nécessite(nt) votre validation manuelle ». |

---

## 2. Stack technique & contraintes

### 2.1 Environnement cible

| Élément | Spécification |
|---------|---------------|
| OS | macOS (Apple Silicon M1/M2/M3 ou Intel) |
| Python | **3.11+** |
| Backend | Python (logique métier, scripts, intégrations) |
| UI | **NiceGUI** (FastAPI + Vue/Quasar) — **validé** |
| Base de données | **SQLite 3** |
| IA documentaire (natif) | **Google Gemini** — `gemini-2.5-flash` via SDK **`google-genai`** |
| IA documentaire (Éco) | **OpenRouter** — `qwen/qwen-2.5-vl-72b-instruct` (configurable) |
| IA documentaire (fallback) | **Ollama** — `llama3.2-vision` (local) |
| Notifications | `osascript` / AppleScript ou lib Python (`pync`, `desktop-notifier`) |
| Prérequis système | **Poppler** via Homebrew (`brew install poppler`) pour conversion PDF |

### 2.2 Choix UI — NiceGUI (validé)

Streamlit a été écarté : excellent pour la data science, mais inadapté au split-view Inbox, au drag & drop fluide et au Kanban interactif. NiceGUI offre la flexibilité nécessaire pour une **vraie application Mac locale**.

| Capacité | NiceGUI |
|----------|---------|
| Drag & drop fichiers | Natif, flexible |
| Layout 2 colonnes (doc + formulaire) | Excellent |
| Kanban / interactions temps réel | Bon |
| App locale | Oui (serveur local, pas de cloud) |

### 2.3 Dépendances Python

```
nicegui>=2.0
httpx                    # OpenRouter + Ollama (fallback)
google-genai             # client Gemini (SDK officiel)
pydantic>=2.0            # validation JSON IA
python-dateutil          # parsing dates
google-api-python-client # Calendar (phase 4)
google-auth-oauthlib
Pillow                   # preview images
pillow-heif              # support HEIC (photos iPhone)
pdf2image                # PDF → image (requiert Poppler)
playwright>=1.49         # Robot Leclerc Drive (Menu & Drive)
weasyprint>=62.0         # Export PDF planning batch cooking
pypdf                    # métadonnées PDF (optionnel)
```

Prérequis système Menu & Drive :

```bash
brew install pango gdk-pixbuf libffi   # WeasyPrint (export PDF planning)
playwright install chromium          # Robot Leclerc Drive
```

Le script `start.command` exporte `DYLD_FALLBACK_LIBRARY_PATH` pour WeasyPrint sur Apple Silicon.

**Configuration `.env`** (voir `.env.example`) :

```env
GEMINI_API_KEY=votre_cle_api_google
# GEMINI_MODEL=gemini-2.5-flash          # optionnel
# OPENROUTER_API_KEY=sk-or-...           # mode Éco (ou Paramètres)
# OPENROUTER_MODEL=qwen/qwen-2.5-vl-72b-instruct
```

Clés Gemini : variable d'environnement → table SQLite (`gemini_api_key`).  
Clés OpenRouter : Paramètres UI ou `OPENROUTER_API_KEY` dans `.env`.

**Relance email (SMTP Gmail)** — voir §8.4 et `config.yaml.example` :

```env
# Mot de passe d'application Google (jamais le mot de passe du compte Gmail)
SMTP_SENDER_EMAIL=ton_email@gmail.com
SMTP_RECIPIENT_EMAIL=ton_email@gmail.com
SMTP_APP_PASSWORD=
```

Fichier optionnel `~/Trankil-v2/config.yaml` (copie de `config.yaml.example`) pour `smtp_server`, `smtp_port`, `sender_email`. Le secret reste dans `.env`.

**Sauvegarde SQLite chiffrée** — voir §2.4.2 et `scripts/backup_db.py` :

```env
BACKUP_GPG_PASSPHRASE=passphrase_robuste_32_caracteres_minimum
RCLONE_REMOTE=gdrive
DB_PATH=~/Trankil-v2/database.sqlite
```

Prérequis système : `brew install rclone gnupg` · remote rclone `gdrive` configuré via `rclone config`.

### 2.4 Lancement

| Méthode | Usage |
|---------|-------|
| `python main.py` | Développement et Terminal |
| **`start.command`** | Double-clic sur le Bureau — confort quotidien entrepreneur |
| **LaunchAgent** | Démarrage automatique au login + relance si crash (`KeepAlive`) |

**Port d'écoute** : par défaut **8080** (`APP_PORT` dans `app/config.py`). Au démarrage, `resolve_listen_port()` teste la disponibilité : si 8080 est occupé, l'app bascule sur le premier port libre suivant (8081…8099, jusqu'à 20 tentatives). NiceGUI ouvre le navigateur sur le port effectivement utilisé ; un avertissement est loggé si le port diffère du défaut. Surcharge explicite : `TRANKIL_PORT` ou `APP_PORT` — erreur si le port demandé est déjà pris.

Le script `start.command` active le venv, purge les `__pycache__`, tente de libérer le port 8080 si une instance IA-Secretaire y tourne déjà, lance l'app (`python -B main.py`). Variables optionnelles : `TRANKIL_LOG_LEVEL=DEBUG`, `TRANKIL_PORT=9000`.

#### 2.4.1 Service LaunchAgent (macOS)

Service **launchd** pour lancer l'app en arrière-plan à chaque connexion utilisateur.

| Élément | Valeur |
|---------|--------|
| Fichier plist | `~/Library/LaunchAgents/com.lala.IA_secretaire.plist` |
| Label | `com.lala.IA_secretaire` |
| Script exécuté | `/Users/lala/Dev/IA_Personal_Secretaire/start.command` |
| Répertoire de travail | `/Users/lala/Dev/IA_Personal_Secretaire` |

**Installation / activation** (après création du plist) :

```bash
launchctl load ~/Library/LaunchAgents/com.lala.IA_secretaire.plist
```

**Vérifier que le service tourne** :

```bash
launchctl list | grep IA_secretaire
# ou
launchctl print "gui/$(id -u)/com.lala.IA_secretaire"
```

**Désactiver le service (temporaire)** — arrêt immédiat, le plist reste en place (pas de relance au prochain login tant qu'il n'est pas rechargé) :

```bash
launchctl unload ~/Library/LaunchAgents/com.lala.IA_secretaire.plist
```

**Désactiver le service (définitif)** — arrêt + suppression du plist :

```bash
launchctl unload ~/Library/LaunchAgents/com.lala.IA_secretaire.plist
rm ~/Library/LaunchAgents/com.lala.IA_secretaire.plist
```

**Réactiver après une désactivation temporaire** :

```bash
launchctl load ~/Library/LaunchAgents/com.lala.IA_secretaire.plist
```

> **Migration** : l'ancien nom `com.lala.trankilv2.plist` est obsolète. S'il existe encore, le retirer avant d'installer le nouveau service :
>
> ```bash
> launchctl unload ~/Library/LaunchAgents/com.lala.trankilv2.plist 2>/dev/null
> rm ~/Library/LaunchAgents/com.lala.trankilv2.plist 2>/dev/null
> ```

#### 2.4.2 Sauvegarde automatisée SQLite → Google Drive

Sauvegarde quotidienne de `~/Trankil-v2/database.sqlite` vers Google Drive, chiffrée avant transfert (« Miroir sécurisé »).

| Élément | Valeur |
|---------|--------|
| Script | `scripts/backup_db.py` |
| Plist modèle | `scripts/com.lala.backup_db.plist` |
| Plist installé | `~/Library/LaunchAgents/com.lala.backup_db.plist` |
| Label | `com.lala.backup_db` |
| Planification | Tous les jours à **03:00** (`StartCalendarInterval`) |
| Remote rclone | `gdrive:Trankil-Backups/` |
| Rétention | 7 jours glissants (`rclone delete --min-age 7d`) |
| Logs | `logs/backup.log` (+ `logs/backup_launchd.log` pour launchd) |

**Pipeline** (5 étapes, erreurs loguées par étape) :

1. **Snapshot** — `sqlite3.backup()` en lecture seule (compatible mode WAL, sans bloquer l'app)
2. **Compression** — `.gz` (niveau 6)
3. **Chiffrement** — GPG symétrique AES256 via `BACKUP_GPG_PASSPHRASE` (`.env`)
4. **Transfert** — `rclone copy` vers `gdrive:Trankil-Backups/`
5. **Rotation** — suppression des fichiers distants de plus de 7 jours

Nom des fichiers distants : `database-YYYYMMDD-HHMMSS.sqlite.gz.gpg`.

**Prérequis** :

```bash
brew install rclone gnupg
rclone config   # créer le remote "gdrive" (OAuth Google Drive)
```

**Test manuel** :

```bash
cd /Users/lala/Dev/IA_Personal_Secretaire
source .venv/bin/activate
python scripts/backup_db.py
tail -20 logs/backup.log
```

**Installation / activation du LaunchAgent** :

```bash
mkdir -p ~/Dev/IA_Personal_Secretaire/logs
cp ~/Dev/IA_Personal_Secretaire/scripts/com.lala.backup_db.plist \
   ~/Library/LaunchAgents/com.lala.backup_db.plist
launchctl load ~/Library/LaunchAgents/com.lala.backup_db.plist
```

**Vérifier** :

```bash
launchctl list | grep backup_db
```

**Déclencher immédiatement** (sans attendre 03:00) :

```bash
launchctl start com.lala.backup_db
```

**Désactiver** :

```bash
launchctl unload ~/Library/LaunchAgents/com.lala.backup_db.plist
```

**Restauration** (app arrêtée) :

```bash
rclone copy gdrive:Trankil-Backups/database-YYYYMMDD-HHMMSS.sqlite.gz.gpg /tmp/
gpg -d /tmp/database-....sqlite.gz.gpg | gunzip > /tmp/database-restored.sqlite
# Vérifier puis remplacer ~/Trankil-v2/database.sqlite
```

---

## 3. Architecture système

### 3.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────┐
│                     NiceGUI (Frontend local)                     │
│   Dashboard (accueil) │ Inbox │ GED/Archives │ Paramètres       │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Application Layer (Python)                  │
│  TaskService │ GEDService │ InboxQueueService │ AutopilotService │
│  GeminiClient │ OllamaClient │ MockOllamaClient │ NotificationService │
│  analysis_client.get_analysis_client() │ db_maintenance          │
│  CalendarSyncService (opt-in, OFF par défaut)                    │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
  SQLite            ~/Trankil-v2/      Gemini API (si clé)
  database.sqlite   Pro|Perso/GED/     ou Ollama :11434
                    .inbox/ (file temp.)
```

### 3.2 Processus applicatif

| Composant | Rôle |
|-----------|------|
| **Main app** (`main.py`) | Point d'entrée NiceGUI ; Dashboard = onglet par défaut ; navigation entre vues |
| **InboxQueueService** | File FIFO asynchrone : upload → analyse IA en arrière-plan → Autopilote ou file manuelle |
| **Background scheduler** | Thread daemon : notifications macOS J-3 / J-1 + **relance email J-1** (`notification_scheduler.py`, `email_scheduler.py`) — app ouverte uniquement en V1 |
| **Services** | Couche métier découplée de l'UI (testable unitairement) |

### 3.3 Emplacement des données (chemin fixe V1)

| Ressource | Chemin |
|-----------|--------|
| Racine utilisateur | **`~/Trankil-v2/`** (fixe, non configurable en V1) |
| GED Pro | `~/Trankil-v2/Pro/GED/` |
| GED Perso | `~/Trankil-v2/Perso/GED/` |
| Base SQLite | `~/Trankil-v2/database.sqlite` |
| Inbox temporaire | `~/Trankil-v2/.inbox/` (fichiers en attente de validation manuelle) |
| Config email | `~/Trankil-v2/config.yaml` (optionnel — voir `config.yaml.example`) |
| Credentials Google | `~/Trankil-v2/.credentials/google_calendar/` (hors git) |
| Mapping Leclerc Drive | `~/Trankil-v2/drive_mapping.json` (mot-clé → produit mémorisé) |
| Profil Playwright Leclerc | `~/Trankil-v2/.leclerc_profile/` (session persistante) |

Sauvegarde : **Time Machine** sur le Mac ; export zip prévu en version ultérieure.

---

## 4. Modèle de données

### 4.1 Schéma SQLite

#### Table `tasks`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER PK | Auto-incrément |
| `title` | TEXT NOT NULL | Action / titre de la tâche |
| `category` | TEXT NOT NULL | `'pro'` \| `'perso'` |
| `date_emission` | DATE NOT NULL | Date inscrite sur le document ou date du jour |
| `date_event` | DATE NULL | Date de l'événement si applicable |
| `deadline` | DATE NULL | **Date limite officielle** extraite du document (sans marge artificielle) |
| `status` | TEXT NOT NULL | `'todo'` \| `'urgent'` \| `'archived'` |
| `completed_at` | DATETIME NULL | Horodatage archivage |
| `document_id` | INTEGER FK NULL | Lien vers `documents.id` (**1 document → N tâches** possible) |
| `raw_summary` | TEXT NULL | Résumé document IA — indexé pour recherche GED |
| `justification_proof` | TEXT NULL | Citation / preuve extraite par l'IA pour la tâche |
| `suggestion` | TEXT NULL | Conseil actionnable IA (ex. numéro à appeler, horaires) |
| `recurrence_pattern` | TEXT NULL | `'daily'` \| `'weekly'` \| `'monthly'` — routine récurrente (spawn à l'archivage) |
| `frequence` | TEXT NULL | `'mensuelle'` \| `'trimestrielle'` \| `'annuelle'` — **récurrence virtuelle** (une seule ligne SQLite) |
| `date_reference` | DATE NULL | Date du premier événement (ancrage récurrence virtuelle) |
| `source_url` | TEXT NULL | URL extraite du document (site web, portail en ligne) |
| `parent_task_id` | INTEGER FK NULL | Lien vers la tâche d'origine d'une routine (`tasks.id`) |
| `calendar_synced` | BOOLEAN DEFAULT 0 | Événement Google créé |
| `calendar_event_id` | TEXT NULL | ID événement Google |
| `created_at` | DATETIME | Création enregistrement |
| `updated_at` | DATETIME | Dernière modification |
| `notes` | TEXT NULL | Notes utilisateur (édition manuelle) |

#### Table `documents`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER PK | |
| `original_filename` | TEXT | Nom fichier à l'upload |
| `stored_path` | TEXT NOT NULL | Chemin relatif depuis `~/Trankil-v2` |
| `mime_type` | TEXT | `application/pdf`, `image/png`, `image/heic`, etc. |
| `file_hash` | TEXT NULL | SHA-256 (déduplication optionnelle) |
| `created_at` | DATETIME | |

#### Table `tags`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE NOT NULL | Ex: `formation`, `facture` (sans `#`) |
| `created_at` | DATETIME | |

#### Table `task_tags` (N-N)

| Colonne | Type |
|---------|------|
| `task_id` | INTEGER FK → tasks |
| `tag_id` | INTEGER FK → tags |
| PRIMARY KEY (`task_id`, `tag_id`) |

#### Table `notifications_log`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER PK | |
| `task_id` | INTEGER FK | |
| `notification_type` | TEXT | `'j_minus_3'` \| `'j_minus_1'` |
| `sent_at` | DATETIME | Évite les doublons |

#### Table `email_reminders_log`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER PK | |
| `task_id` | INTEGER FK | |
| `reminder_date` | DATE | Date d'envoi de la relance email |
| `sent_at` | DATETIME | |
| UNIQUE (`task_id`, `reminder_date`) | | Idempotence par jour |

#### Table `settings`

| Colonne | Type | Description |
|---------|------|-------------|
| `key` | TEXT PK | |
| `value` | TEXT | JSON sérialisé si besoin |

Clés settings :

| Clé | Défaut | Description |
|-----|--------|-------------|
| `ollama_model` | `"llama3.2-vision"` | Modèle vision Ollama (fallback) |
| `ollama_base_url` | `"http://localhost:11434"` | URL Ollama (fallback) |
| `gemini_model` | `"gemini-2.5-flash"` | Modèle Gemini (legacy settings ; défaut code) |
| `gemini_api_key` | `""` | Clé API Gemini (alternative au `.env`) |
| `active_ia_provider` | `"Gemini (Natif)"` | Moteur principal : `Gemini (Natif)` \| `OpenRouter (Éco)` |
| `openrouter_api_key` | `""` | Clé API OpenRouter (mode Éco) |
| `openrouter_model` | `"qwen/qwen-2.5-vl-72b-instruct"` | Modèle vision OpenRouter |
| `autopilot_enabled` | `"true"` | Validation automatique post-analyse |
| `google_calendar_auto_sync` | `"false"` | Sync Calendar à la validation (**OFF par défaut**) |
| `notification_enabled` | `"true"` | Relances macOS J-3 / J-1 |
| `email_reminder_enabled` | `"true"` | Relance email proactive J-1 |
| `smtp_server` | `"smtp.gmail.com"` | Serveur SMTP |
| `smtp_port` | `"587"` | Port SMTP (STARTTLS) |
| `sender_email` | `""` | Expéditeur Gmail |
| `recipient_email` | `""` | Destinataire (vide = même adresse) |
| `email_reminder_last_sent_date` | `""` | Idempotence envoi quotidien |

### 4.2 Règles métier — Statut des tâches

Le statut affiché dans le Kanban est **calculé** à partir de `deadline`, `completed_at` et de la date courante :

```
SI completed_at IS NOT NULL → ARCHIVÉ
SINON SI deadline IS NOT NULL ET (deadline < aujourd'hui OU deadline <= aujourd'hui + 48h) → EN RETARD / URGENT
SINON → À FAIRE
  └─ Sous-section « Sans date » en bas de colonne si deadline IS NULL
```

**Tâche sans deadline** : reste dans « À FAIRE », affichée dans une sous-section **« Sans date »** en bas de colonne (ne pollue pas le tri chronologique du haut).

**Tri chronologique Kanban** (implémenté dans `app/utils/dates.py`, appliqué dans `dashboard_view.py` à chaque rendu) :

| Colonne | Règle de tri | Justification |
|---------|--------------|---------------|
| **EN RETARD / URGENT** | `deadline` **ASC** (plus ancienne en haut) | Une échéance du 01/05 est plus critique qu'une du 28/05 |
| **À FAIRE** (partie datée) | `deadline` **ASC** (échéance la plus proche en haut) | Attirer le regard sur les actions imminentes |
| **Sans date** | Toujours **en bas** de « À FAIRE » | `deadline IS NULL` → bucket séparé `todo_no_date` |

Fonctions utilitaires :
- `sort_kanban_urgent(tasks)` → `sorted(..., key=lambda t: t.deadline or date.max)`
- `sort_kanban_todo(tasks)` → `sorted(..., key=lambda t: (t.deadline is None, t.deadline or date.max))`

**Marge utilisateur** : la deadline en base est la **date officielle** du document. La marge est gérée par le **système de relance** (alertes J-3 et J-1), pas par une modification de la donnée stockée.

**Multi-tâches** : un même document peut produire plusieurs tâches (ex. courrier avec plusieurs échéances). Toutes partagent le même `document_id` après validation.

**Routines récurrentes (spawn)** : une tâche manuelle peut porter un `recurrence_pattern` (`daily` / `weekly` / `monthly`). Lors de l'archivage (« Fait »), la prochaine occurrence est **créée** automatiquement ; `parent_task_id` pointe vers la tâche racine.

**Récurrence virtuelle (projection)** : une tâche (document ou manuelle) peut porter un `frequence` (`mensuelle` / `trimestrielle` / `annuelle`). **Une seule ligne** en base — pas de duplication annuelle. Au « Fait », `deadline` et `date_event` sont reportées via `calculer_prochaine_echeance()` ; la tâche reste active (`completed_at = NULL`). `date_reference` mémorise la date du premier événement. Priorité à `frequence` sur `recurrence_pattern` dans `archive_task()`.

### 4.3 Index recommandés

```sql
CREATE INDEX idx_tasks_deadline ON tasks(deadline);
CREATE INDEX idx_tasks_category ON tasks(category);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_documents_stored_path ON documents(stored_path);
CREATE INDEX idx_tasks_raw_summary ON tasks(raw_summary);  -- recherche GED
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);    -- routines récurrentes
```

---

## 5. Vue principale — Tableau de bord unifié

> **Onglet par défaut** au lancement · route NiceGUI `/` · fichier `app/ui/dashboard_view.py`

### 5.1 Structure de la page

La page est divisée en **deux sections verticales** :

```
┌─────────────────────────────────────────────────────────────┐
│  ▼ Dépôt de documents & Statut  (ui.expansion — repliable)   │
│  ┌──────────────┬──────────────┬──────────────────────────┐ │
│  │ Coller ⌘V    │ Glisser-dép. │ Création manuelle/Routine│ │
│  └──────────────┴──────────────┴──────────────────────────┘ │
│  [spinner NiceGUI + message d'état IA]                       │
├─────────────────────────────────────────────────────────────┤
│  [bannière validation manuelle Inbox — toujours visible]     │
├─────────────────────────────────────────────────────────────┤
│  SECTION BASSE — Filtres + Vue (Kanban ou Liste)             │
│  Filtrer : [Tout] [Pro] [Perso]   #tag1 #tag2 …             │
│  Vue : [Kanban ▤] [Liste ≡]                                  │
│  ┌─────────────┬─────────────┬─────────────┐  (mode Kanban) │
│  │ EN RETARD   │ À FAIRE     │ ARCHIVÉ     │                 │
│  └─────────────┴─────────────┴─────────────┘                 │
│  — ou tableau dense lignes alternées (mode Liste) —           │
└─────────────────────────────────────────────────────────────┘
```

**Pas de prévisualisation document** sur cette vue — écran volontairement épuré.

### 5.2 Panneau escamotable (`ui.expansion`)

La zone haute est un **accordéon NiceGUI** (`ui.expansion`) pour maximiser l'espace vertical du Kanban :

| Propriété | Valeur |
|-----------|--------|
| Titre | « Dépôt de documents & Statut » |
| Icône | `cloud_upload` |
| État par défaut | **Déplié** (`value=True`) au premier chargement |
| Style en-tête | Texte gras, fond blanc (`google_theme.py`), bordure discrète |
| Comportement | Clic sur l'en-tête → repli/dépli animé (Quasar) |

**Auto-dépliage** : si un fichier est en cours d'analyse IA, le panneau se rouvre automatiquement pour afficher le spinner.

La **bannière validation manuelle Inbox** (§5.5) reste **hors** du panneau, visible même replié.

### 5.3 Dépôt de documents (3 colonnes)

Modules : `app/ui/document_upload.py` (`create_document_intake`) + `app/ui/manual_task_form.py`.

| Colonne | Composant | Comportement |
|---------|-----------|--------------|
| **1 — Coller** | `create_paste_zone()` | Focus → ⌘V / Ctrl+V envoie l'image au pipeline |
| **2 — Glisser-déposer** | `ui.upload` | `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, **`.heic`** |
| **3 — Création manuelle** | Formulaire compact | Tâche sans document GED (§5.4) |

Traitement fichiers : copie dans `~/Trankil-v2/.inbox/{uuid}_{original_name}` → enqueue `InboxQueueService`.

Layout `ui.row` à **3 colonnes égales** (`triple_column=True`), contenu entièrement **à l'intérieur** du `ui.expansion`.

### 5.4 Création manuelle & routines récurrentes

Formulaire « Création manuelle / Routine » (`manual_task_form.py`) :

| Champ | Widget | Description |
|-------|--------|-------------|
| Titre / Action | `ui.input` | Obligatoire — placeholder neutre « Titre de la tâche » |
| Catégorie | `ui.radio` | Pro / Perso |
| Date de départ | `ui.input type=date` | Première échéance → `deadline` |
| Récurrence | `ui.select` | Aucune, Quotidien, Hebdomadaire, Mensuel |
| Suggestion / Note | `ui.input` | Optionnel |
| Action | `ui.button` | « Créer la tâche » (icône `add`) |

Service : `create_manual_task()` dans `task_service.py`.

**Récurrence classique à l'archivage** (`recurrence_pattern`) — logique dans `app/utils/recurrence.py` :

| Pattern SQLite | Libellé UI | Prochaine échéance |
|----------------|------------|-------------------|
| `daily` | Quotidien | +1 jour |
| `weekly` | Hebdomadaire | +7 jours |
| `monthly` | Mensuel | +1 mois (`relativedelta`) |

Lors du clic « Fait » : archivage + **insertion** de la prochaine occurrence. Badge **🔁 Quotidien/Hebdomadaire/Mensuel** sur les cartes Kanban.

**Récurrence virtuelle** (`frequence`) — logique dans `app/utils/frequence.py` :

| Valeur SQLite | Libellé UI | Prochaine échéance |
|---------------|------------|-------------------|
| `mensuelle` | Mensuelle | +1 mois |
| `trimestrielle` | Trimestrielle | +3 mois |
| `annuelle` | Annuelle | +1 an |

Lors du clic « Fait » : **même ligne** mise à jour (`deadline` / `date_event` avancées, statut recalculé). Icône **`refresh`** violette sur cartes Kanban et vue Liste. Configurable aussi depuis le modal **Modifier la tâche** (dropdown Récurrence).

**Enrichissement URL** : si `source_url` est renseigné (IA ou édition manuelle), lien **URL** cliquable (nouvel onglet) sur cartes Kanban et vue Liste ; champ « Lien externe » + bouton « Aller sur le site » dans le modal d'édition.

Migration SQLite : colonnes `recurrence_pattern`, `parent_task_id`, `frequence`, `date_reference`, `source_url` ajoutées via `migrations.py` au démarrage.

### 5.5 Indicateur « En cours de traitement »

Pendant l'analyse IA (file FIFO), **à l'intérieur du panneau déplié** :

- **Spinner** NiceGUI (`ui.spinner` line, taille `lg`)
- Texte d'état :
  - En attente : `En attente — [Nom_du_fichier]`
  - En cours : `Analyse de [Nom_du_fichier] par [Moteur (modèle)] en cours…` (ex. `OpenRouter (qwen/qwen-2.5-vl-72b-instruct)`, `Gemini (gemini-2.5-flash)`)
- Blocage double-envoi pendant une analyse en cours
- À la fin : repli optionnel du panneau + **rafraîchissement instantané** du Kanban

Transitions non bloquantes : analyse en `asyncio.to_thread`, garde-fous client NiceGUI (`inbox_ui_safe.py`).

### 5.6 Bannière validation manuelle

Affichée **sous** le panneau escamotable si `manual_pending_count() > 0` :

```
⚠️ N document(s) nécessite(nt) votre validation manuelle.
[Cliquez ici pour aller à l'Inbox]
```

Le bouton bascule l'onglet Inbox via `tabs.value = inbox_tab`.

### 5.7 Filtres globaux

| Filtre | Comportement |
|--------|--------------|
| **Tout** | Toutes catégories |
| **Pro uniquement** | `category = 'pro'` |
| **Perso uniquement** | `category = 'perso'` |
| **Méta-tags** | Chips cliquables ; multi-sélection en logique **OR** |

### 5.8 Vue bi-mode — Kanban & Liste

Sélecteur discret sous les chips (`vue_mode, set_vue_mode = ui.state('kanban')` dans `dashboard_view.py`) :

| Mode | Icône | Usage |
|------|-------|-------|
| **Kanban** (défaut) | `view_kanban` | Visualisation flux, urgence, colonnes |
| **Liste** | `list` | Grille haute densité — scan vertical type gestion de projet |

#### 5.8.1 Vue Liste — « Wide Layout » (grille 12 colonnes)

Regroupement par **lots** (même `document_id` ou création manuelle) via `_group_tasks_into_batches()` · tri `sort_list_view_tasks()`.

**En-tête fixe** aligné sur la grille (`gap-x-4`, `items-center`) :

| Colonnes | Libellé | Contenu |
|----------|---------|---------|
| **1–6** | Tâche | Badge Pro/Perso + icône `refresh` si récurrence virtuelle + titre (gras) + lien **URL** si `source_url` ; enfants : flèche `subdirectory_arrow_right`, indentation `pl-4`, `text-sm text-gray-500` |
| **7–8** | Deadline | Icône `alarm` + date (`format_date_fr`) ou `—` |
| **9–10** | Événement | Icône `calendar_today` + `date_event` ou `—` |
| **11** | Conseil IA | Icône `lightbulb` + texte tronqué (`truncate`, tooltip au survol) ou `—` |
| **12** | *(actions)* | Checkbox « Fait » + suppression |

**Blocs lot** (`render_list_batch_block`) :

```
┌─ border-l-4 (couleur lot) ─────────────────────────────────────────┐
│  [Pro] Tâche mère (bg-white, py-3)     │ ⏰ │ 📅 │ 💡 │ ☐ 🗑      │
├────────────────────────────────────────┼────┼────┼────┼───────────┤
│    ↳ Enfant 1 (bg-gray-50/50, py-2)    │ …  │ …  │ …  │ ☐ 🗑      │
└────────────────────────────────────────┴────┴────┴────┴───────────┘
```

| Élément | Style |
|---------|-------|
| Conteneur lot | `bg-white rounded-xl border border-gray-200 mb-6` + `batch_border_left_classes()` |
| Tâche mère | Fond blanc, `py-3` |
| Tâches enfants | Fond `bg-gray-50/50`, séparateur `border-t border-gray-100`, `py-2` compact |
| Dates | `text-xs text-gray-400`, icônes espacées (`gap-2`) |

**Actions lot** (tâche mère, lot ≥ 2 tâches) : bouton `delete_sweep` → dialogue « Supprimer tout le lot » → `delete_tasks()` (transaction SQLite).

Tri : lots regroupés, échéances proches en haut. Tâches archivées visibles uniquement en mode Kanban (colonne ARCHIVÉ).

### 5.9 Colonnes Kanban

| Colonne | Contenu | Style |
|---------|---------|-------|
| **EN RETARD / URGENT** | Non archivées, deadline passée ou ≤ 48h | Carte bordure rouge gauche, badge urgence |
| **À FAIRE** | Non archivées, deadline > 48h | Tri **deadline ASC** (proche en haut) |
| ↳ *Sans date* | Non archivées, `deadline IS NULL` | Sous-section en **bas** de la colonne « À FAIRE » |
| **ARCHIVÉ** | `completed_at` renseigné | Badge vert discret |

**Ordre d'affichage** (post-bucketing, avant rendu) :

1. **Urgent** : deadline la plus ancienne / la plus en retard en **première** position.
2. **À faire** : deadline future la plus **proche** en haut ; tâches sans deadline reléguées sous le séparateur « Sans date ».

Implémentation : `sort_kanban_urgent()` et `sort_kanban_todo()` dans `app/utils/dates.py` ; tests dans `tests/test_task_status.py`.

### 5.10 Carte tâche

```
[Pro] [↻] Déclaration URSSAF              [URL]
📧 28/05/2026
• Date événement : 10/06/2026
• Deadline : 10/06/2026
💡 Déclarer en ligne avant échéance
• Tags : #urssaf #cotisation
☐ Fait    [Modifier] [@ GED] [Suppr.]    [📅 Sync Calendar]
```

- Fond **pastel par lot document** (`BATCH_PASTEL_PALETTE`, `task_card_classes()`)
- Date de réception : icône mail + pilule uniquement (sans libellé « Reçu le »)
- **Récurrence virtuelle** : icône `refresh` (tooltip Mensuelle / Trimestrielle / Annuelle)
- **Lien externe** : texte **URL** cliquable si `source_url` renseigné (nouvel onglet)

Interactions :
- **Checkbox « Fait »** → archivage simple ; si `recurrence_pattern` → spawn prochaine occurrence ; si `frequence` → report échéance sur la même ligne (notification « Échéance reportée »)
- **Bouton « Modifier »** → modal d'édition (`task_edit_dialog.py`) — champs **Récurrence** (dropdown) et **Lien externe (URL)**
- **Bouton « @ »** (`alternate_email`) → ouvre le fichier GED associé (`open_file` macOS) ; masqué si pas de `stored_path`
- **Bouton « Suppr. »** → suppression définitive (fichier GED conservé)
- **Sync Calendar** → création événement manuelle (§10)

### 5.11 Rafraîchissement

- Recalcul colonne « Urgent » à chaque chargement et toutes les **60 s** (timer NiceGUI)
- **Re-tri chronologique** des colonnes Urgent et À faire à chaque rafraîchissement Kanban
- Rafraîchissement à chaque changement d'onglet (`tab_registry.py`)
- Rafraîchissement Kanban **ou Liste** à chaque événement de la file d'analyse, création manuelle ou archivage récurrent

### 5.12 Thème visuel — Google Workspace

Module central : `app/ui/google_theme.py` — palette Google Clean & Bright, injectée via `apply_google_theme()` dans `main.py`.

| Élément | Style |
|---------|-------|
| **Fond page** | Gris très clair `#f9fafb` |
| **Header** | Blanc, icône `task_alt`, titre gris foncé |
| **Navigation** | Onglets pill-shaped (pilules arrondies, indicateur masqué) |
| **Filtres catégorie** | Chips `Tout / Pro / Perso` (noir, bleu, vert selon actif) |
| **Cartes tâche** | Pastel Google Keep par lot + ombre légère ; urgent = bordure rouge gauche |
| **Vue Liste** | Grille 12 col. wide layout · blocs lot `border-l-4` · colonnes Deadline / Événement / Conseil IA alignées |
| **Toggle vue** | Boutons pill `trankil-view-toggle` |
| **Métadonnées dates** | Icône grise + pilule grise (`trankil-date-pill`) |
| **Suggestion IA** | Encart ambre avec icône ampoule |
| **Actions carte** | Icônes grises discrètes (modifier, supprimer, calendrier) |

Helpers exportés : `task_card_classes()`, `batch_border_left_classes()`, `view_toggle_classes()`, `render_date_meta()`, etc.

---

## 6. Vue secondaire — Inbox (validation manuelle)

> **Onglet second** dans la navigation · fichier `app/ui/inbox_view.py`  
> Rôle : **rattrapage / mode manuel** lorsque l'Autopilote est désactivé ou en cas d'erreur d'analyse.

### 6.1 Comportement

1. Zone **coller image** + **drag-and-drop** (même module `document_upload.py`, layout vertical).
2. **File d'analyse asynchrone** : plusieurs documents peuvent être en queue ; traitement IA sérialisé en arrière-plan (moteur sélectionné dans Paramètres).
3. Affichage **split-view** pour chaque job prêt :
   - **Gauche** : preview document (image directe ; HEIC converti ; PDF → **page 1 uniquement**).
   - **Droite** : **fiches multi-tâches** éditables (1 document → N tâches).
4. Bouton **« Valider et Classer »** :
   - Renomme et déplace le fichier vers GED (§7).
   - Crée `documents` + N `tasks` (+ tags, `justification_proof`, `suggestion`).
   - Retire le job de la file.
   - Sync Calendar auto si activée dans Paramètres.

### 6.2 Schéma JSON attendu de l'IA (multi-tâches)

```json
{
  "tasks": [
    {
      "title": "Séance de formation (1/3)",
      "date_emission": "2026-05-28",
      "date_event": "2026-11-05",
      "deadline": "2026-11-05",
      "category": "pro",
      "tags": ["formation"],
      "justification_proof": "« Séances de formation obligatoires les 5, 12 et 19 novembre »",
      "suggestion": "Horaires : 14h à 16h",
      "frequence": null,
      "source_url": null,
      "confidence": 0.85
    },
    {
      "title": "Conférence de clôture formation",
      "date_emission": "2026-05-28",
      "date_event": "2026-11-22",
      "deadline": "2026-11-22",
      "category": "pro",
      "tags": ["formation"],
      "justification_proof": "« Conférence de clôture le samedi 22 novembre »",
      "suggestion": "Réservation par mail ou au 01.02.03.04.05",
      "confidence": 0.80
    }
  ],
  "document_summary": "Mail organisme avec plusieurs dates de formation.",
  "confidence": 0.82
}
```

Format mono-tâche (legacy) normalisé automatiquement par `normalize_analysis_payload()`.

### 6.3 Règles de parsing & fallback

| Champ | Règle |
|-------|-------|
| `date_emission` | Extraire du document ; si absent → date du jour (timezone locale Mac) |
| `deadline` | Extraire la **date officielle** telle qu'inscrite sur le document. **Pas de marge en base.** |
| `category` | `pro` par défaut si ambigu ; l'utilisateur corrige |
| `tags` | 1 à 5 tags, capitalisation normalisée (`app/utils/tags.py`) |
| `document_summary` | Résumé global du document ; **persisté** via `raw_summary` sur chaque tâche liée |
| `justification_proof` | Citation ou extrait justifiant la tâche |
| `suggestion` | Conseil actionnable court pour l'utilisateur |
| `frequence` | Récurrence détectée → `mensuelle` \| `trimestrielle` \| `annuelle` ; sinon `null` (normalisation Pydantic) |
| `source_url` | URL complète (`https://…`) si site web visible sur le document ; préfixe `https://` ajouté si absent |

Post-traitement : `task_expansion.py` (ancrage temporel relatif), inférence suggestion de secours (`suggestion_infer.py`). Champs `frequence` et `source_url` persistés à la validation Inbox et en Autopilote.

### 6.4 Mode mock (sans IA configurée)

Si ni Gemini (clé absente) ni Ollama (modèle absent / injoignable) :
- **Mock uniquement** — pas d'autre modèle de secours.
- Retourne une tâche générique dérivée du nom de fichier.
- Bandeau UI Inbox : « Mode démo — Ollama non disponible » (si client mock actif).

### 6.5 Champs formulaire (UI Inbox)

| Champ | Widget | Éditable |
|-------|--------|----------|
| Titre / Action | Input text | Oui |
| Date d'émission | Date picker | Oui |
| Date événement | Date picker (optionnel) | Oui |
| Deadline | Date picker | Oui |
| Catégorie | Radio Pro / Perso | Oui |
| Tags | Input texte | Oui |
| Suggestion | Input texte | Oui |
| Preuve IA | Label lecture seule | Non |

Possibilité d'**exclure** des fiches avant validation (indices exclus dans le job).

---

## 7. Vue 3 — GED / Archives

### 7.1 Convention de nommage

```
{YYYY-MM-DD}_{Slug-Titre}.{ext}
```

Exemples :
- `2026-05-28_Mail_Formation.png`
- `2026-05-15_Courrier_URSSAF_Cotisations.pdf`

**Slug** : titre sanitizé (ASCII, underscores, max 60 caractères).

### 7.2 Recherche

- Champ recherche full-text sur : titre tâche, tags, nom fichier, **`raw_summary`**.
- Filtres : catégorie, tags (OR), plage dates émission.
- Tri : date émission DESC par défaut.
- Résultat : liste + preview au clic.

### 7.3 Intégrité

- Le chemin en base (`documents.stored_path`) est la **source de vérité**.
- Si fichier manquant sur disque → badge « Fichier introuvable » + chemin attendu.

---

## 8. Vue 4 — Menu & Drive

Onglet **Menu & Drive** : saisie du menu hebdomadaire, génération IA du planning batch cooking + liste de courses, export PDF vers GED Perso, robot Playwright Leclerc Drive.

### 8.1 Saisie

**Mise en page** : trois blocs côte à côte sur une seule ligne (`col-4`, sans retour à la ligne) — **Plats enfants** | **Régime spécial (hôte additionnel)** | **Choses à ajouter** (+ commentaires).

| Zone | Contenu |
|------|---------|
| Premier jour | Select Lundi→Dimanche — réordonne templates et checkboxes |
| Plats enfants | Mode **Saisie manuelle** ou **Consignes IA** |
| Convives enfants | Nombre (défaut 4) — plats |
| Créneaux enfants | Grille 7 jours × (Midi \| Soir) — colonnes par jour, cases **M** / **S** avec infobulle (manuel **et** consignes) |
| Consignes enfants | Textarea multiligne (mode consignes) — contraintes libres pour l'IA ; bouton **Effacer consigne pour l'IA** |
| Template repas | Textarea préfixé — **uniquement les créneaux cochés** ; saisie manuelle ou miroir post-génération ; contenu des créneaux décochés conservé en cache |
| Régime spécial (hôte additionnel) | Mode **Saisie manuelle** ou **Consignes IA** (défaut consignes) |
| Convives hôte régime | Nombre (défaut 1) — menu distinct des enfants |
| Créneaux hôte régime | Même grille jour × (Midi \| Soir), flux séparé |
| Consignes hôte régime | Textarea multiligne (mode consignes) — ex. anti-constipation, sans lactose ; bouton **Effacer consigne pour l'IA** |
| Template hôte régime | Textarea préfixé — **créneaux cochés uniquement** (cache identique au flux enfants) |
| Extras | Saisie libre (essuie-tout, couches, etc.) |
| Commentaires | Notes libres (persistées, non envoyées à l'IA) |

**Boutons d'effacement** :

| Bouton | Effet |
|--------|--------|
| **Effacer cette colonne** (enfants / régime) | Réinitialise le template aux préfixes des créneaux cochés — ne touche ni mode, ni consignes, ni cases |
| **Effacer consigne pour l'IA** | Vide le textarea consignes (visible en mode Consignes IA) |
| **Effacer cette colonne** (extras) | Vide extras + commentaires |
| **TOUT EFFACER** | Réinitialise toute la session Menu & Drive |

**Deux flux repas parallèles** : mêmes créneaux horaires, menus distincts. L'hôte au régime spécial est traité comme un convive additionnel qui mange différemment (ex. enfants : fajitas ; hôte : salade verte + haricots verts).

**Modes de saisie (Enfants / Hôte régime)** :

| Mode | Comportement |
|------|--------------|
| Saisie manuelle | Créneaux cochés + template préfixé — seules les lignes remplies sont envoyées |
| Consignes IA | Consignes + créneaux cochés vides → l'IA invente les plats lors de la génération |

**Hybride courant** : enfants en saisie manuelle + hôte régime en consignes IA sur les mêmes créneaux cochés. Un créneau rempli manuellement est prioritaire ; les créneaux cochés vides sont complétés par l'IA.

**Génération consolidée** : un seul appel IA (`analyze_drive_menu`) produit `planning_repas` (enfants) + `planning_regime` (hôte) + `liste_courses`. Miroir post-génération dans les templates.

**Persistance** : `~/Trankil-v2/current_menu.json` — modes, consignes, `enfants_creneaux_cibles`, `regime_creneaux_cibles`, templates, résultats. Migration automatique des anciens `regime_jours_cibles` (7 jours) vers créneaux midi/soir.

Lignes vides ou égales au préfixe seul sont ignorées avant envoi IA (`build_drive_menu_input`).

### 8.2 Génération IA

- Factory **`get_drive_analysis_client()`** : Gemini ou OpenRouter selon `active_ia_provider` (Paramètres) — **pas Ollama, pas Mock**.
- Repli croisé cloud si le provider choisi est indisponible.
- Modèle Pydantic `DriveMenuAnalysisResult` : `planning_repas[]` + `planning_regime[]` (`PlanningRepasItem` : `jour`, `moment`, `plat`, `batch_cooking_dimanche`, `action_minute`) + `liste_courses[]` (`CourseItem`).
- **Batch cooking unifié** : l'IA rédige `batch_cooking_dimanche` (préparation le **premier jour de la semaine**, clé JSON historique) comme un bloc opérationnel compact par jour ; texte identique enfant/hôte lorsque la préparation est commune (affichage PDF fusionné par jour).
- **L'IA ne génère plus de HTML** — data JSON pure uniquement ; le template HTML/CSS printanier est assemblé côté Python (`drive_pdf_service.render_planning_html`).
- Mots-clés épurés (ex. `oeufs`, `jambon blanc`) sans packaging (`douzaine`, `en tranche`, etc.).
- Date du planning calculée par Python (`compute_menu_week_sunday`) — injectée dans le prompt user et le PDF local.
- Post-traitement : filtrage créneaux autorisés enfants/régime, déduplication courses, normalisation rayons/jours/moments, tri des plannings.

### 8.3 Restitution interactive

Après génération IA :

| Zone | Contenu |
|------|---------|
| Colonne gauche | **Planning Batch Cooking** — même grille HTML que le PDF (voir § 8.4) ; bouton **Imprimer / Sauvegarder en GED** |
| Colonne droite | Tableau courses haute densité par rayon (§ 8.3.1) |

#### 8.3.1 Tableau courses

Après génération IA, colonne droite : tableau haute densité par rayon :

| Colonne | Comportement |
|---------|--------------|
| Checkbox | Coché par défaut ; décocher exclut du robot |
| Quantité | `ui.number` éditable |
| Article | `mot_cle` IA |
| Lien Leclerc Drive | URL mémorisée (`drive_mapping.json`) ou champ vide bordure orange ; collage → sauvegarde immédiate mapping |

### 8.4 Export PDF

- **Template HTML local** (`drive_pdf_service.py`) — grille **jours en colonnes**, sous-colonnes **Midi | Soir** :
  - Ligne **Enfants** : plat + action jour J par créneau
  - Ligne **Convives régime** : plat + action jour J par créneau (même bloc, visuellement séparé)
  - Ligne **Batch {premier jour}** : un bloc unifié par jour (`colspan=2`), texte blanc sur fond vert ; colonne du premier jour de la semaine en **gras**
  - Seuls les jours contenant au moins un créneau planifié sont affichés
- Même rendu à l'écran (carte Planning Batch Cooking) et en PDF. Format A4 paysage. CSS printanier fixe (#166534, #f0fdf4).
- WeasyPrint → `~/Trankil-v2/Perso/GED/` avec nommage GED standard.
- Prérequis macOS : `brew install pango gdk-pixbuf libffi` + `DYLD_FALLBACK_LIBRARY_PATH` dans `start.command`.
- Modifier le look du PDF = éditer le template Python local, sans regénérer via l'IA.

### 8.5 Robot Leclerc Drive — stratégie URL `#plus`

| Phase | Comportement |
|-------|--------------|
| Connexion | `launch_persistent_context` sur `~/.leclerc_profile` ; ouverture magasin Roques-sur-Garonne ; pause `[▶️ Démarrer les courses]` |
| Courses | **Uniquement bypass URL** : pour chaque article coché avec URL, `page.goto(url#plus)` × `quantite` — ajout auto panier Leclerc ; **aucune recherche** pour produits mémorisés |
| Sans URL | Produit reporté dans `produits_a_valider` sans bloquer la boucle |
| Apprentissage | Bip macOS ; recherche lente (`delay=180`) ; utilisateur ouvre la fiche produit ; capture `page.url` → `drive_mapping.json` ; mise à jour tableau UI en temps réel ; bouton [Passer] |
| Stop | `🛑 STOPPER LE ROBOT` annule `_robot_task` ; fermeture propre navigateur (`context.close()`) |
| Erreurs réseau | `try/except` sur `goto` → produit en échec / mapping supprimé si URL expirée |

Modèle robot : `DriveShoppingItem` (`CourseItem` + `product_url` optionnelle).

Mapping : `drive_mapping.json` : `{ mot_cle: { product_id, product_url, product_name } }` — URLs stockées sans `#plus`.

Simulation humaine : pauses 1,5–3,0 s après chaque `#plus`. Logs préfixés `[LeclercBot]`.

---

## 9. Automatisations

### 8.1 Mode Autopilote

Service : `app/services/autopilot_service.py`

| Étape | Action |
|-------|--------|
| 1 | Analyse IA terminée (`JobStatus.READY`) |
| 2 | Si `autopilot_enabled == "true"` → `auto_validate_job()` |
| 3 | Crée N tâches + archive GED + sync Calendar si auto activée |
| 4 | Supprime le job de la file ; notifie ; rafraîchit Dashboard |
| Échec autopilote | Job reste en file ; bannière validation manuelle |

Toggle dans **Paramètres** : « Autopilote (validation automatique) » — **ON par défaut**.

### 8.2 Routines récurrentes

Service : `create_manual_task()` + `archive_task()` dans `task_service.py`

| Type | Calcul dates | Comportement au « Fait » |
|------|--------------|--------------------------|
| **Classique** (`recurrence_pattern`) | `app/utils/recurrence.py` | Archivage + insertion prochaine occurrence (`parent_task_id` = racine) |
| **Virtuelle** (`frequence`) | `app/utils/frequence.py` · `calculer_prochaine_echeance()` | Même ligne : `deadline` / `date_event` avancées, tâche reste active |

| Événement | Action |
|-----------|--------|
| Clic « Créer la tâche » | Insertion tâche manuelle sans `document_id` ; `deadline` = date de départ |
| Clic « Fait » + `recurrence_pattern` | Archivage + insertion prochaine occurrence avec `parent_task_id` = racine |
| Clic « Fait » + `frequence` | Report échéance sur la même ligne (zéro duplication en base) |

### 8.3 Relances anti-oubli (macOS)

| Déclencheur | Condition | Action |
|-------------|-----------|--------|
| J-3 | `deadline - today == 3 jours`, tâche non archivée, notif pas déjà envoyée | Notification système |
| J-1 | idem à J-1 | Notification + carte dashboard en rouge vif |

Message type :
```
⚠️ Trankil-v2 : Il te reste 3 jours pour « [Titre de la tâche] ».
```

Implémentation V1 :
- Thread daemon au démarrage app, boucle toutes les **30 min**.
- **Uniquement tant que l'application est ouverte.**
- Log dans `notifications_log` pour idempotence.

**V1.1** : daemon `launchd` pour notifications macOS même app fermée.

### 8.4 Relance proactive par email (Gmail)

Service : `app/services/email_scheduler.py` · configuration : `get_email_config()` dans `config.py`, Paramètres UI, `~/Trankil-v2/config.yaml`, `.env` (`SMTP_APP_PASSWORD`).

| Déclencheur | Condition | Action |
|-------------|-----------|--------|
| J-1 (email) | Tâches actives (`todo` / `urgent`, non archivées) dont `deadline == demain` | **Un seul email par jour** regroupant toutes les tâches concernées |

**Objet** (1 tâche) : `🚨 Secrétaire iA_Rappel : Tâche urgente pour demain - [Titre]`  
**Objet** (N tâches) : `🚨 Secrétaire iA_Rappel : N tâches urgentes pour demain`

**Corps** : rappel personnalisé avec titre(s) et date(s) d'échéance formatées (`format_date_fr`).

Implémentation :
- SMTP Gmail (`smtp.gmail.com:587`, STARTTLS) via `smtplib`
- **Mot de passe d'application Google** obligatoire (pas le mot de passe du compte)
- Intégré au planificateur existant (`process_email_reminders()` appelé par `notification_scheduler.py`)
- Idempotence : setting `email_reminder_last_sent_date` + log `email_reminders_log`
- **try/except** réseau/SMTP — l'app ne plante pas si internet est coupé

Toggle Paramètres : « Relance proactive par email (Gmail) » — dépend aussi de `notification_enabled`.

### 8.5 Google Calendar Sync

Voir §10.

---

## 10. Intégration IA — Gemini, OpenRouter, Ollama & mock

### 9.1 Factory client (`get_analysis_client`)

Ordre de priorité (`app/services/analysis_client.py`) selon **`active_ia_provider`** (Paramètres) :

| Priorité | Client | Condition |
|----------|--------|-----------|
| 1 | **OpenRouterClient** | Provider = `OpenRouter (Éco)` **et** clé OpenRouter présente |
| 2 | **GeminiClient** | `GEMINI_API_KEY` présente (`.env` ou `settings`) |
| 3 | **OllamaClient** | Ollama joignable + modèle `llama3.2-vision` installé |
| 4 | **MockOllamaClient** | Aucune IA disponible |

Libellé moteur UI : `describe_analysis_engine(client)` → affiché dans le spinner Dashboard.

Modules partagés :
- `analysis_prompt.py` — `build_gemini_system_prompt()` (Gemini) · `build_system_prompt()` (OpenRouter / Ollama)
- `analysis_pipeline.py` — sanitization JSON (titres ≤ 8 mots), validation Pydantic, expansion dates, logs

### 9.2 Configuration Gemini (natif)

```yaml
gemini:
  api_key: ${GEMINI_API_KEY}
  model: gemini-2.5-flash   # surchargeable via GEMINI_MODEL (.env)
```

SDK : **`google-genai`** · `genai.Client` · `temperature=0.0` · JSON strict : `response_mime_type=application/json` + schéma Pydantic `DocumentAnalysisResult`.

### 9.3 Flux d'analyse Gemini

1. Charger clé API (`config.get_gemini_api_key()`).
2. Préparer l'image : PDF → page 1 PNG, HEIC → PNG (`load_image_bytes_for_vision`).
3. Appel multimodal via `client.models.generate_content()` + `types.Part.from_bytes`.
4. Prompt système : `build_gemini_system_prompt()` (règles anti-monologue, max 8 mots titre, **extraction URL + récurrence**).
5. Parser JSON → `finalize_document_analysis()`.

### 9.4 Configuration OpenRouter (mode Éco)

Paramètres UI ou `.env` :

```yaml
openrouter:
  api_key: ${OPENROUTER_API_KEY}   # ou settings.openrouter_api_key
  model: qwen/qwen-2.5-vl-72b-instruct
  endpoint: https://openrouter.ai/api/v1/chat/completions
```

Flux (`openrouter_client.py`) : `httpx` POST compatible OpenAI Vision · image base64 data-URL · `response_format: json_object` · `temperature=0.0` · headers `Authorization` + `HTTP-Referer` · même pipeline Pydantic que Gemini.

### 9.5 Configuration Ollama (fallback local)

```yaml
ollama:
  base_url: http://localhost:11434
  model: llama3.2-vision
  timeout_seconds: 120
```

Flux : image base64 → API `/api/chat` avec `format: json` · `build_system_prompt()` · pipeline post-traitement commun.

### 9.6 Prompt système (résumé)

**Gemini** (`build_gemini_system_prompt`) :
- Titres factuels, **max 8 mots**, interdiction monologue dans le JSON
- Une tâche par date distincte · ancrage année courante
- Suggestion logistique ultra-courte

**OpenRouter / Ollama** (`build_system_prompt`) : même logique, formulation légèrement adaptée au fallback local.

### 9.7 PDF — Page 1 uniquement (V1)

Conversion page 1 en image (`pdf2image` + **Poppler**) puis envoi au modèle vision.

### 9.8 HEIC — Photos iPhone (V1)

Support natif via **`pillow-heif`** : conversion transparente HEIC → preview + analyse vision.

---

## 11. Intégration Google Calendar

### 10.1 Périmètre V1

- OAuth 2.0 desktop flow (Google Cloud Console).
- Scopes : `https://www.googleapis.com/auth/calendar.events`
- Calendrier cible : **primary**
- **Sync automatique OFF par défaut**
- Procédure documentée dans le **README**

### 10.2 Création événement

| Champ Google | Valeur |
|--------------|--------|
| Titre | `[PRO] Titre tâche (Limite: 26 Juin)` |
| Date | `deadline` en all-day event |
| Description | `Document reçu le 28/05/2026. Tags: #tag1, #tag2.` |

### 10.3 UX

- Bouton **« Synchroniser l'agenda »** sur carte tâche Dashboard
- Switch global **Paramètres** : sync auto à la validation (désactivé par défaut)
- Sync auto également déclenchée par l'Autopilote si l'option est activée

### 10.4 Paramètres — maintenance données

Section **« Données locales »** (`settings_view.py`) :

| Élément | Description |
|---------|-------------|
| Compteur | Tâches, documents, tags, notifications en base |
| Bouton **Vider la base SQLite** | Supprime données métier ; **conserve** `settings` (Autopilote, clés, Calendar) |
| Effet | Vide aussi la file d'analyse en mémoire ; rafraîchit Dashboard, Inbox, GED |
| Hors périmètre | Fichiers GED sur disque et dossier `.inbox` **non** supprimés |

Service : `app/services/db_maintenance.py` (`purge_application_data`, `get_application_data_counts`).

### 10.5 Hors-ligne (Calendar)

- Si pas de credentials : bouton grisé + message de configuration

---

## 12. Arborescence projet

```
IA_Personal_Secretaire/          # dépôt git
├── spec.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── main.py                      # entrypoint NiceGUI — Dashboard onglet défaut
├── config.yaml.example          # modèle SMTP Gmail → ~/Trankil-v2/config.yaml
├── start.command                # double-clic Bureau (purge __pycache__ + python -B)
├── app/
│   ├── config.py                # constantes (ROOT_PATH, APP_PORT, resolve_listen_port)
│   ├── db/
│   │   ├── connection.py
│   │   ├── schema.sql
│   │   └── migrations.py        # migrations incrémentales + backfill
│   ├── models/
│   │   ├── task.py
│   │   ├── analysis.py          # DocumentAnalysisResult multi-tâches
│   │   ├── drive.py             # DriveMenuAnalysisResult Menu & Drive
│   │   └── archive.py
│   ├── services/
│   │   ├── task_service.py      # validate_inbox_tasks (1 doc → N tasks)
│   │   ├── ged_service.py
│   │   ├── archive_service.py
│   │   ├── inbox_queue.py       # file FIFO async IA
│   │   ├── autopilot_service.py # validation automatique
│   │   ├── analysis_client.py   # factory IA + get_drive_analysis_client (Menu & Drive)
│   │   ├── analysis_prompt.py     # prompts Gemini / OpenRouter / Ollama
│   │   ├── analysis_pipeline.py   # post-traitement JSON IA
│   │   ├── drive_prompt.py        # prompts Menu & Drive
│   │   ├── drive_analysis_pipeline.py
│   │   ├── drive_pdf_service.py   # WeasyPrint → GED Perso
│   │   ├── drive_mapping_service.py
│   │   ├── leclerc_driver.py      # robot Playwright Leclerc Drive
│   │   ├── gemini_client.py       # Google Gemini (google-genai)
│   │   ├── openrouter_client.py   # OpenRouter / Qwen VL (mode Éco)
│   │   ├── ollama_client.py       # fallback local
│   │   ├── mock_ollama_client.py
│   │   ├── task_expansion.py    # ancrage dates relatives
│   │   ├── db_maintenance.py    # purge SQLite
│   │   ├── notification_service.py
│   │   ├── email_scheduler.py   # relance email J-1 (SMTP Gmail)
│   │   ├── notification_scheduler.py
│   │   └── calendar_service.py
│   ├── ui/
│   │   ├── dashboard_view.py    # page d'accueil — Kanban / Liste bi-mode
│   │   ├── google_theme.py      # thème Google Workspace (CSS + helpers)
│   │   ├── inbox_view.py        # validation manuelle split-view
│   │   ├── document_upload.py   # dépôt + collage (2 ou 3 colonnes)
│   │   ├── manual_task_form.py  # création manuelle / routines
│   │   ├── inbox_ui_safe.py     # garde-fous client NiceGUI
│   │   ├── ged_view.py
│   │   ├── drive_view.py        # Menu & Drive — menu, IA, robot Leclerc
│   │   ├── settings_view.py
│   │   ├── task_edit_dialog.py
│   │   ├── task_badges.py       # icône récurrence + lien URL + notifications « Fait »
│   │   ├── calendar_button.py
│   │   └── tab_registry.py
│   └── utils/
│       ├── dates.py             # colonnes Kanban + tri chronologique + tri Liste
│       ├── tags.py
│       ├── slugify.py
│       ├── file_preview.py
│       ├── recurrence.py        # patterns daily/weekly/monthly (spawn)
│       ├── frequence.py         # récurrence virtuelle mensuelle/trimestrielle/annuelle
│       ├── suggestion_infer.py
│       └── analysis_logging.py
├── logs/                        # backup.log (gitignored)
├── scripts/
│   ├── init_db.py
│   ├── backup_db.py             # sauvegarde SQLite → GPG → Google Drive
│   ├── com.lala.backup_db.plist # modèle LaunchAgent (03:00 daily)
│   └── check_ollama.py
└── tests/                       # 94+ tests unitaires (conftest isolation SQLite)
```

---

## 13. Plan d'implémentation itérative

### Phase 0 — Fondations ✅
- [x] Initialiser dépôt, `pyproject.toml`, `.gitignore`
- [x] Créer `~/Trankil-v2` au premier lancement
- [x] Schéma SQLite + migrations incrémentales
- [x] `OllamaClient` + `MockOllamaClient` + **`GeminiClient`**
- [x] Factory `get_analysis_client()` (Gemini → Ollama → mock)
- [x] Tests isolés (`tests/conftest.py` — pas de pollution `~/Trankil-v2`)
- [x] Tests unitaires statut tâche + slug GED
- [x] `start.command`

### Phase 1 — Inbox & analyse ✅
- [x] Drag & drop NiceGUI (PDF, PNG, JPG, HEIC)
- [x] Collage presse-papiers (⌘V)
- [x] Preview document (PDF p1, HEIC, images)
- [x] Analyse IA multi-tâches (Gemini prioritaire, Ollama ou mock)
- [x] File d'attente asynchrone (`InboxQueueService`)
- [x] Validation → GED + N tasks + raw_summary en base

### Phase 2 — Dashboard ✅
- [x] Kanban 3 colonnes + sous-section « Sans date »
- [x] Filtres Pro/Perso + tags (OR)
- [x] Checkbox archivage + bouton **Modifier** + suppression
- [x] **Interface unifiée** : dépôt + statut + Kanban sur une page
- [x] Dashboard = page d'accueil par défaut
- [x] Mode **Autopilote** + bannière validation manuelle
- [x] **3 colonnes** : collage, dépôt, création manuelle / routines
- [x] **Panneau escamotable** (`ui.expansion`) pour la zone haute
- [x] Récurrence quotidienne / hebdomadaire / mensuelle à l'archivage

### Phase 3 — GED / Archives ✅
- [x] Recherche full-text (incl. raw_summary)
- [x] Preview & ouverture Finder

### Phase 4 — Automatisations ✅
- [x] Notifications J-3 / J-1 (app ouverte)
- [x] **Relance email J-1** (SMTP Gmail, regroupement multi-tâches)
- [x] Google Calendar OAuth + sync manuelle + option auto

### Phase 5 — Polish 🔄
- [x] Settings UI (Autopilote, sync Calendar, notifications, email SMTP, **purge SQLite**)
- [x] **Multi-IA** : sélecteur Gemini / OpenRouter (Éco) + clés dans Paramètres
- [x] Migration SDK **`google-genai`** · modèle `gemini-2.5-flash` · température 0
- [x] Gestion erreurs lifecycle NiceGUI (`inbox_ui_safe`)
- [x] **Port d'écoute dynamique** — fallback automatique si 8080 occupé (`resolve_listen_port`)
- [x] Suggestions IA (`suggestion`, `justification_proof`)
- [x] Tâches manuelles + colonnes récurrence SQLite
- [x] Cartes Kanban : affichage **date événement**
- [x] **Tri chronologique Kanban** : urgent (deadline ASC) + à faire (proche en haut, sans date en bas)
- [x] **Thème Google Workspace** (`google_theme.py`) — header blanc, chips, cartes pastel par lot
- [x] **Vue Liste wide layout** — grille 12 col., blocs lot, suppression groupée (`delete_tasks`)
- [x] Ouverture GED (@) depuis les cartes Kanban
- [x] **Récurrence virtuelle** — `frequence` mensuelle/trimestrielle/annuelle, report échéance sans duplication SQLite
- [x] **Enrichissement URL** — extraction IA `source_url`, lien cliquable Kanban/Liste, édition manuelle
- [ ] README complet à jour avec workflow Dashboard-first

### Backlog V1.1+
- [x] LaunchAgent `com.lala.IA_secretaire` — démarrage auto au login (§ 2.4.1)
- [x] Sauvegarde SQLite chiffrée → Google Drive — GPG + rclone + LaunchAgent 03:00 (§ 2.4.2)
- [ ] Daemon `launchd` pour notifications app fermée
- [ ] Chemin racine configurable
- [ ] Refactor Inbox pour réutiliser entièrement `create_document_intake`

---

## 14. Décisions validées (arbitrages Architecte)

| Domaine | Décision |
|---------|----------|
| **Nom UI** | **Trankil-v2** (dépôt git : `IA_Personal_Secretaire`) |
| **Page d'accueil** | **Tableau de bord unifié** — Inbox reléguée au mode manuel |
| **Autopilote** | **ON par défaut** — validation auto post-analyse |
| **Langue** | Français uniquement V1, pas d'i18n |
| **UI framework** | **NiceGUI** validé à 100 % |
| **Filtre tags** | **OR** (union) |
| **Sans deadline** | Colonne « À FAIRE », sous-section **« Sans date »** en bas |
| **Édition tâche** | **Oui** — bouton « Modifier » sur chaque carte |
| **Fichiers / tâches** | **1 document → N tâches** possible |
| **Chemin racine** | **`~/Trankil-v2` fixe** V1 |
| **PDF** | **Page 1** uniquement V1 |
| **Poppler** | Prérequis Homebrew, documenté README |
| **Lancement** | `python main.py` + **`start.command`** sur le Bureau + **LaunchAgent** `com.lala.IA_secretaire` (optionnel, § 2.4.1) |
| **Modèle IA natif** | **Gemini** (`gemini-2.5-flash`) via SDK `google-genai` |
| **Modèle IA Éco** | **OpenRouter** — Qwen VL (`qwen/qwen-2.5-vl-72b-instruct`) |
| **Sélecteur moteur** | Paramètres → `active_ia_provider` |
| **Fallback IA** | Gemini → **Ollama** local → **Mock** démo |
| **raw_summary** | **Stocké en base**, indexé pour recherche GED |
| **Suggestion IA** | Champ `suggestion` affiché sur cartes Dashboard (💡) |
| **Dashboard** | **Bi-mode** : Kanban (défaut) + **Vue Liste** (grille 12 col., blocs lot) |
| **Suppression lot** | Vue Liste : `delete_sweep` sur tâche mère → `delete_tasks()` |
| **Relances** | macOS J-3/J-1 + **email J-1** (Gmail SMTP, 1 mail/jour regroupé) |
| **Deadline en base** | **Date officielle** du document ; marge = relances J-3/J-1 + email J-1 |
| **Google Calendar** | **OFF par défaut**, bouton manuel ; procédure README |
| **Notifications V1** | **App ouverte uniquement** ; launchd en V1.1 |
| **HEIC** | **Oui V1** via `pillow-heif` |
| **Backup SQLite** | **GPG symétrique + rclone** → `gdrive:Trankil-Backups/`, rotation 7 jours, LaunchAgent 03:00 (§ 2.4.2) |
| **Preview Dashboard** | **Non** — écran épuré ; preview réservée à l'Inbox |
| **Zone dépôt Dashboard** | **Panneau `ui.expansion`** repliable — 3 colonnes à l'intérieur |
| **Tâches manuelles** | **Oui** — sans document GED, depuis colonne 3 du Dashboard |
| **Routines récurrentes** | **Oui** — daily / weekly / monthly (spawn) ; **récurrence virtuelle** mensuelle / trimestrielle / annuelle (projection, une ligne) |
| **Enrichissement URL** | Champ `source_url` extrait par IA ou saisi manuellement ; lien **URL** sur cartes Dashboard |
| **Purge données** | Bouton Paramètres — vide SQLite métier, conserve settings |

---

## 15. Critères d'acceptation (MVP → V1)

### MVP (Phase 0–1) ✅

- [x] Déposer un PNG/PDF/HEIC → champs pré-remplis (Gemini, Ollama ou mock).
- [x] Analyse IA produit un JSON multi-tâches valide (Gemini / OpenRouter JSON + Pydantic).
- [x] Modifier et valider → fichier dans `Pro/GED/` ou `Perso/GED/` avec bon nommage.
- [x] `raw_summary` persisté et searchable.

### MVP étendu (Phase 2) ✅

- [x] Tâche visible dans Dashboard, bonne colonne selon deadline.
- [x] Tâches sans deadline en sous-section « Sans date ».
- [x] Cocher « Fait » → Archivé.
- [x] Filtrer Pro / Perso / tags (OR).
- [x] Bouton « Modifier » fonctionnel.
- [x] Dépôt + collage depuis le Dashboard sans passer par l'Inbox.
- [x] Spinner et rafraîchissement Kanban post-analyse.
- [x] Autopilote + bannière validation manuelle.
- [x] Création manuelle + routines récurrentes depuis le Dashboard.
- [x] Panneau escamotable « Dépôt de documents & Statut ».
- [x] Tri chronologique : urgences les plus anciennes en haut ; échéances proches avant les sans date.

### V1 complète (Phase 4–5) ✅ / 🔄

- [x] Recherche GED (titre + raw_summary + tags).
- [x] Notifications J-3 et J-1 sur Mac (app ouverte).
- [x] Relance email J-1 (Gmail, mot de passe d'application).
- [x] Vue Liste Dashboard — grille wide layout (Deadline, Événement, Conseil IA, suppression lot).
- [x] Récurrence virtuelle : « Fait » reporte l'échéance sans créer de nouvelle ligne.
- [x] URL documentaire : détection IA + lien cliquable + correction manuelle dans « Modifier ».
- [x] Sync Google Calendar manuelle + option auto (OFF par défaut).
- [x] Toggle Autopilote dans Paramètres.
- [x] Purge SQLite depuis Paramètres (données métier uniquement).
- [ ] README complet : workflow Dashboard-first, Ollama, Poppler, HEIC, Google Calendar, `start.command`.

---

## Annexe A — Exemple document type

> Flyer association avec inscription spectacle **avant le 10/06/2026** et répétition le **12/06/2026**.  
> → **2 tâches** créées depuis un seul document.  
> → Catégorie Pro, tags Spectacle / Répétition, deadlines officielles extraites.  
> → Suggestions IA affichées sur les cartes Dashboard.  
> → Relances automatiques à J-3 et J-1 (macOS) + email J-1 pour chaque deadline.

## Annexe B — Commandes dev

```bash
# Prérequis système
brew install poppler

# Installation
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

# Init base & dossiers
python scripts/init_db.py

# Lancer l'app
python main.py
# ou double-clic sur start.command
# ou LaunchAgent com.lala.IA_secretaire (démarrage auto au login — voir § 2.4.1)

# Configuration IA (copier .env.example → .env)
cp .env.example .env
# Éditer GEMINI_API_KEY=... et/ou OPENROUTER_API_KEY=...

# Configuration email (copier config.yaml.example → ~/Trankil-v2/config.yaml)
# SMTP_APP_PASSWORD=...  # mot de passe d'application Google dans .env

# Sauvegarde SQLite chiffrée (prérequis : brew install rclone gnupg && rclone config)
# BACKUP_GPG_PASSPHRASE=...  # dans .env
# python scripts/backup_db.py
# LaunchAgent : voir § 2.4.2

# Vérifier Ollama (fallback optionnel)
python scripts/check_ollama.py
ollama pull llama3.2-vision

# Tests
pytest tests/ -q
```

---

**État actuel** : V1 fonctionnelle avec **multi-IA** (Gemini natif + OpenRouter Éco), fallback Ollama, Dashboard **bi-mode** (Kanban + **Vue Liste wide layout**), cartes pastel par lot, relances macOS + **email J-1**, Autopilote, routines récurrentes, LaunchAgent app + **sauvegarde SQLite chiffrée Google Drive**, purge SQLite, isolation tests SQLite et **89+ tests** pytest. Prochaine étape recommandée : finaliser le README.
