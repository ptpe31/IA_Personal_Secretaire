# Trankil-v2 — Spécification Technique & Fonctionnelle

> **Version** : 0.5-implemented  
> **Date** : 29 mai 2026  
> **Statut** : V1 fonctionnelle — analyse Gemini, fallback Ollama, purge SQLite  
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
8. [Automatisations](#8-automatisations)
9. [Intégration IA — Gemini, Ollama & mock](#9-intégration-ia--gemini-ollama--mock)
10. [Intégration Google Calendar](#10-intégration-google-calendar)
11. [Arborescence projet](#11-arborescence-projet)
12. [Plan d'implémentation itérative](#12-plan-dimplémentation-itérative)
13. [Décisions validées (arbitrages Architecte)](#13-décisions-validées-arbitrages-architecte)
14. [Critères d'acceptation (MVP → V1)](#14-critères-dacceptation-mvp--v1)

---

## 1. Vision & Principes

### 1.1 Objectif produit

**Trankil-v2** est un assistant/secrétaire virtuel **local-first** pour Mac, destiné à un jeune entrepreneur. Il transforme courriers scannés, photos iPhone et captures d'écran en **tâches actionnables**, les organise dans un **tableau de bord Kanban**, archive les documents dans une **GED structurée**, et déclenche des **relances** et une **sync agenda** optionnelle.

Le dépôt de développement s'appelle `IA_Personal_Secretaire` ; l'application affichée et le dossier utilisateur portent le nom **Trankil-v2**.

### 1.2 Principes non négociables

| Principe | Description |
|----------|-------------|
| **Local-first (données)** | SQLite + filesystem local sous `~/Trankil-v2` ; pas de compte obligatoire. |
| **Analyse documentaire** | **Gemini API** si clé configurée (multimodal cloud) ; sinon **Ollama** local ; sinon **mock** démo. |
| **Mac natif** | Notifications macOS, chemin fixe `~/Trankil-v2`. |
| **Itératif** | MVP testable sans IA (mode mock), enrichissement progressif. |
| **Français V1** | Interface en français uniquement ; pas d'i18n en V1. |

### 1.3 Persona & workflow quotidien (référence UX)

**Depuis V0.3** : le **Tableau de bord** est la page d'accueil (`/`). L'Inbox n'est plus un passage obligatoire.

```
[Courrier PDF] ──► Scanner ──┐
[Photo iPhone] ──► HEIC ────┤
[Mail capture] ──► PNG ─────┤──► Dashboard (dépôt) ──► Analyse IA ──► Kanban + GED
                             │         (Gemini → Ollama → mock)
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
| IA documentaire (prioritaire) | **Google Gemini** — `gemini-1.5-flash` (configurable) via `google-generativeai` |
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
httpx                    # client Ollama (fallback)
google-generativeai      # client Gemini (analyse prioritaire)
pydantic>=2.0            # validation JSON IA
python-dateutil          # parsing dates
google-api-python-client # Calendar (phase 4)
google-auth-oauthlib
Pillow                   # preview images
pillow-heif              # support HEIC (photos iPhone)
pdf2image                # PDF → image (requiert Poppler)
pypdf                    # métadonnées PDF (optionnel)
```

**Configuration Gemini** : fichier `.env` à la racine du dépôt (voir `.env.example`) :

```env
GEMINI_API_KEY=votre_cle_api_google
# GEMINI_MODEL=gemini-1.5-pro   # optionnel
```

La clé peut aussi être stockée dans `settings` (`gemini_api_key`). Priorité : variable d'environnement → table SQLite.

### 2.4 Lancement

| Méthode | Usage |
|---------|-------|
| `python main.py` | Développement et Terminal |
| **`start.command`** | Double-clic sur le Bureau — confort quotidien entrepreneur |

Le script `start.command` active le venv, purge les `__pycache__`, libère le port 8080 si occupé, lance l'app (`python -B main.py`) et ouvre le navigateur sur `http://localhost:8080`. Variable optionnelle : `TRANKIL_LOG_LEVEL=DEBUG`.

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
| **Background scheduler** | Thread daemon : vérifie deadlines, envoie notifications J-3 / J-1 (**app ouverte uniquement en V1**) |
| **Services** | Couche métier découplée de l'UI (testable unitairement) |

### 3.3 Emplacement des données (chemin fixe V1)

| Ressource | Chemin |
|-----------|--------|
| Racine utilisateur | **`~/Trankil-v2/`** (fixe, non configurable en V1) |
| GED Pro | `~/Trankil-v2/Pro/GED/` |
| GED Perso | `~/Trankil-v2/Perso/GED/` |
| Base SQLite | `~/Trankil-v2/database.sqlite` |
| Inbox temporaire | `~/Trankil-v2/.inbox/` (fichiers en attente de validation manuelle) |
| Credentials Google | `~/Trankil-v2/.credentials/google_calendar/` (hors git) |

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
| `recurrence_pattern` | TEXT NULL | `'daily'` \| `'weekly'` \| `'monthly'` — routine récurrente |
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
| `gemini_model` | `"gemini-1.5-flash"` | Modèle Gemini (`gemini-1.5-pro` possible) |
| `gemini_api_key` | `""` | Clé API Gemini (alternative au `.env`) |
| `autopilot_enabled` | `"true"` | Validation automatique post-analyse |
| `google_calendar_auto_sync` | `"false"` | Sync Calendar à la validation (**OFF par défaut**) |
| `notification_enabled` | `"true"` | Relances J-3 / J-1 |

### 4.2 Règles métier — Statut des tâches

Le statut affiché dans le Kanban est **calculé** à partir de `deadline`, `completed_at` et de la date courante :

```
SI completed_at IS NOT NULL → ARCHIVÉ
SINON SI deadline IS NOT NULL ET (deadline < aujourd'hui OU deadline <= aujourd'hui + 48h) → EN RETARD / URGENT
SINON → À FAIRE
  └─ Sous-section « Sans date » en bas de colonne si deadline IS NULL
```

**Tâche sans deadline** : reste dans « À FAIRE », affichée dans une sous-section **« Sans date »** en bas de colonne (ne pollue pas le tri chronologique du haut).

**Marge utilisateur** : la deadline en base est la **date officielle** du document. La marge est gérée par le **système de relance** (alertes J-3 et J-1), pas par une modification de la donnée stockée.

**Multi-tâches** : un même document peut produire plusieurs tâches (ex. courrier avec plusieurs échéances). Toutes partagent le même `document_id` après validation.

**Routines récurrentes** : une tâche manuelle peut porter un `recurrence_pattern`. Lors de l'archivage (« Fait »), la prochaine occurrence est créée automatiquement avec la même routine ; `parent_task_id` pointe vers la tâche racine.

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
│  SECTION BASSE — Filtres + Kanban                            │
│  Filtrer : [Tout] [Pro] [Perso]   #tag1 #tag2 …             │
│  ┌─────────────┬─────────────┬─────────────┐                 │
│  │ EN RETARD   │ À FAIRE     │ ARCHIVÉ     │                 │
│  └─────────────┴─────────────┴─────────────┘                 │
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
| Style en-tête | Texte gras, fond gris clair (`bg-grey-2`), bordure discrète |
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

**Récurrence à l'archivage** (`archive_task()`) — logique dans `app/utils/recurrence.py` :

| Pattern SQLite | Libellé UI | Prochaine échéance |
|----------------|------------|-------------------|
| `daily` | Quotidien | +1 jour |
| `weekly` | Hebdomadaire | +7 jours |
| `monthly` | Mensuel | +1 mois (`relativedelta`) |

Lors du clic « Fait » sur une tâche récurrente : archivage + création immédiate de la prochaine occurrence (`todo`) avec même titre, catégorie, suggestion et `recurrence_pattern`. Badge **🔁 Quotidien/Hebdomadaire/Mensuel** sur les cartes Kanban.

Migration SQLite : colonnes `recurrence_pattern` et `parent_task_id` ajoutées via `migrations.py` au démarrage.

### 5.5 Indicateur « En cours de traitement »

Pendant l'analyse IA (file FIFO), **à l'intérieur du panneau déplié** :

- **Spinner** NiceGUI (`ui.spinner` — dots + line, taille `lg`)
- Texte d'état :
  - En attente : `En attente — [Nom_du_fichier]`
  - En cours : `⚙️ Analyse de [Nom_du_fichier] par la secrétaire IA en cours...`
- À la fin : disparition du spinner + **rafraîchissement instantané** des colonnes Kanban

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

### 5.8 Colonnes Kanban

| Colonne | Contenu | Style |
|---------|---------|-------|
| **EN RETARD / URGENT** | Non archivées, deadline passée ou ≤ 48h | Fond rouge, badge urgence |
| **À FAIRE** | Non archivées, deadline > 48h | Tri deadline ASC |
| ↳ *Sans date* | Non archivées, `deadline IS NULL` | Sous-section en **bas** de la colonne « À FAIRE » |
| **ARCHIVÉ** | `completed_at` renseigné | Vert discret |

### 5.9 Carte tâche

```
[Pro] Séance de formation (1/3)              [🔁 Mensuel]
• Reçu le : 28/05/2026
• Deadline : 05/11/2026
💡 Horaires : 14h à 16h
• Tags : #formation #organisme
☐ Fait    [Modifier]    [Suppr.]    [📅 Sync Calendar]
```

Interactions :
- **Checkbox « Fait »** → archivage ; si récurrente → prochaine occurrence créée automatiquement
- **Bouton « Modifier »** → modal d'édition (`task_edit_dialog.py`)
- **Bouton « Suppr. »** → suppression définitive (fichier GED conservé)
- **Sync Calendar** → création événement manuelle (§10)

### 5.10 Rafraîchissement

- Recalcul colonne « Urgent » à chaque chargement et toutes les **60 s** (timer NiceGUI)
- Rafraîchissement à chaque changement d'onglet (`tab_registry.py`)
- Rafraîchissement Kanban à chaque événement de la file d'analyse, création manuelle ou archivage récurrent

---

## 6. Vue secondaire — Inbox (validation manuelle)

> **Onglet second** dans la navigation · fichier `app/ui/inbox_view.py`  
> Rôle : **rattrapage / mode manuel** lorsque l'Autopilote est désactivé ou en cas d'erreur d'analyse.

### 6.1 Comportement

1. Zone **coller image** + **drag-and-drop** (même module `document_upload.py`, layout vertical).
2. **File d'analyse asynchrone** : plusieurs documents peuvent être en queue ; traitement Ollama sérialisé en arrière-plan.
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

Post-traitement : `task_expansion.py` (ancrage temporel relatif), inférence suggestion de secours (`suggestion_infer.py`).

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

## 8. Automatisations

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

Service : `create_manual_task()` + `archive_task()` dans `task_service.py` · calcul dates : `app/utils/recurrence.py`

| Événement | Action |
|-----------|--------|
| Clic « Créer la tâche » | Insertion tâche manuelle sans `document_id` ; `deadline` = date de départ |
| Clic « Fait » + `recurrence_pattern` | Archivage + insertion prochaine occurrence avec `parent_task_id` = racine |

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

**V1.1** : daemon `launchd` pour notifications même app fermée.

### 8.4 Google Calendar Sync

Voir §10.

---

## 9. Intégration IA — Gemini, Ollama & mock

### 9.1 Factory client (`get_analysis_client`)

Ordre de priorité (`app/services/analysis_client.py`) :

| Priorité | Client | Condition |
|----------|--------|-----------|
| 1 | **GeminiClient** | `GEMINI_API_KEY` présente (`.env` ou `settings`) |
| 2 | **OllamaClient** | Ollama joignable + modèle `llama3.2-vision` installé |
| 3 | **MockOllamaClient** | Aucune IA disponible |

Modules partagés :
- `analysis_prompt.py` — prompt système + few-shot formation multi-tâches (ancrage 2026)
- `analysis_pipeline.py` — sanitization JSON, validation Pydantic, expansion dates, logs

### 9.2 Configuration Gemini

```yaml
gemini:
  api_key: ${GEMINI_API_KEY}   # .env ou settings.gemini_api_key
  model: gemini-1.5-flash      # ou gemini-1.5-pro via settings / env
```

SDK : `google-generativeai` · JSON strict : `response_mime_type=application/json` + schéma Pydantic `DocumentAnalysisResult` (sanitisé via `gemini_response_schema()` — retrait de `minItems`, etc., incompatibles avec le proto Gemini).

### 9.3 Flux d'analyse Gemini

1. Charger clé API (`config.get_gemini_api_key()`).
2. Préparer l'image : PDF → page 1 PNG, HEIC → PNG (`load_image_bytes_for_vision`).
3. Appel multimodal : prompt utilisateur + bytes image (PNG/JPEG/WebP).
4. Prompt système : `build_system_prompt()` (few-shot séances de formation).
5. Parser JSON → `finalize_document_analysis()` (expansion, normalisation tags).

### 9.4 Configuration Ollama (fallback local)

```yaml
ollama:
  base_url: http://localhost:11434
  model: llama3.2-vision
  timeout_seconds: 120
```

Flux : image base64 → API `/api/chat` avec `format: json` · même prompt et pipeline post-traitement que Gemini.

### 9.5 Prompt système (résumé)

```
Tu es un assistant secrétaire pour un entrepreneur français.
Analyse ce document et extrais TOUTES les tâches actionnables distinctes.
Réponds UNIQUEMENT en JSON valide avec :
- tasks[] : title, date_emission, date_event, deadline, category, tags,
  justification_proof, suggestion, confidence
- document_summary, confidence
Dates : YYYY-MM-DD. deadline = date officielle du document, sans marge.
```

Few-shot complet (4 tâches « séances de formation ») dans `analysis_prompt.py`.

### 9.6 PDF — Page 1 uniquement (V1)

Conversion page 1 en image (`pdf2image` + **Poppler**) puis envoi au modèle vision.

### 9.7 HEIC — Photos iPhone (V1)

Support natif via **`pillow-heif`** : conversion transparente HEIC → preview + analyse vision.

---

## 10. Intégration Google Calendar

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

## 11. Arborescence projet

```
IA_Personal_Secretaire/          # dépôt git
├── spec.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── main.py                      # entrypoint NiceGUI — Dashboard onglet défaut
├── start.command                # double-clic Bureau (purge __pycache__ + python -B)
├── app/
│   ├── config.py                # constantes (ROOT_PATH fixe)
│   ├── db/
│   │   ├── connection.py
│   │   ├── schema.sql
│   │   └── migrations.py        # migrations incrémentales + backfill
│   ├── models/
│   │   ├── task.py
│   │   ├── analysis.py          # DocumentAnalysisResult multi-tâches
│   │   └── archive.py
│   ├── services/
│   │   ├── task_service.py      # validate_inbox_tasks (1 doc → N tasks)
│   │   ├── ged_service.py
│   │   ├── archive_service.py
│   │   ├── inbox_queue.py       # file FIFO async IA
│   │   ├── autopilot_service.py # validation automatique
│   │   ├── analysis_client.py   # factory Gemini → Ollama → mock
│   │   ├── analysis_prompt.py     # prompt système partagé
│   │   ├── analysis_pipeline.py   # post-traitement JSON IA
│   │   ├── gemini_client.py       # client Google Gemini
│   │   ├── ollama_client.py       # fallback local
│   │   ├── mock_ollama_client.py
│   │   ├── task_expansion.py    # ancrage dates relatives
│   │   ├── db_maintenance.py    # purge SQLite
│   │   ├── notification_service.py
│   │   ├── notification_scheduler.py
│   │   └── calendar_service.py
│   ├── ui/
│   │   ├── dashboard_view.py    # page d'accueil — expansion + Kanban
│   │   ├── inbox_view.py        # validation manuelle split-view
│   │   ├── document_upload.py   # dépôt + collage (2 ou 3 colonnes)
│   │   ├── manual_task_form.py  # création manuelle / routines
│   │   ├── inbox_ui_safe.py     # garde-fous client NiceGUI
│   │   ├── ged_view.py
│   │   ├── settings_view.py
│   │   ├── task_edit_dialog.py
│   │   ├── calendar_button.py
│   │   └── tab_registry.py
│   └── utils/
│       ├── dates.py
│       ├── tags.py
│       ├── slugify.py
│       ├── file_preview.py
│       ├── recurrence.py        # patterns daily/weekly/monthly
│       ├── suggestion_infer.py
│       └── analysis_logging.py
├── scripts/
│   ├── init_db.py
│   └── check_ollama.py
└── tests/                       # 62+ tests unitaires (conftest isolation SQLite)
```

---

## 12. Plan d'implémentation itérative

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
- [x] Google Calendar OAuth + sync manuelle + option auto

### Phase 5 — Polish 🔄
- [x] Settings UI (Autopilote, sync Calendar, notifications, **purge SQLite**)
- [x] Gestion erreurs lifecycle NiceGUI (`inbox_ui_safe`)
- [x] Suggestions IA (`suggestion`, `justification_proof`)
- [x] Tâches manuelles + colonnes récurrence SQLite
- [ ] README complet à jour avec workflow Dashboard-first

### Backlog V1.1+
- [ ] Daemon `launchd` pour notifications app fermée
- [ ] Export backup zip `~/Trankil-v2`
- [ ] Chemin racine configurable
- [ ] Refactor Inbox pour réutiliser entièrement `create_document_intake`

---

## 13. Décisions validées (arbitrages Architecte)

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
| **Lancement** | `python main.py` + **`start.command`** sur le Bureau |
| **Modèle IA prioritaire** | **Gemini** (`gemini-1.5-flash`) si `GEMINI_API_KEY` configurée |
| **Fallback IA** | **Ollama** local → **Mock** démo |
| **raw_summary** | **Stocké en base**, indexé pour recherche GED |
| **Suggestion IA** | Champ `suggestion` affiché sur cartes Dashboard (💡) |
| **Deadline en base** | **Date officielle** du document ; marge = relances J-3/J-1 |
| **Google Calendar** | **OFF par défaut**, bouton manuel ; procédure README |
| **Notifications V1** | **App ouverte uniquement** ; launchd en V1.1 |
| **HEIC** | **Oui V1** via `pillow-heif` |
| **Backup zip** | Plus tard (Time Machine suffit) |
| **Preview Dashboard** | **Non** — écran épuré ; preview réservée à l'Inbox |
| **Zone dépôt Dashboard** | **Panneau `ui.expansion`** repliable — 3 colonnes à l'intérieur |
| **Tâches manuelles** | **Oui** — sans document GED, depuis colonne 3 du Dashboard |
| **Routines récurrentes** | **Oui** — daily / weekly / monthly ; prochaine occurrence à l'archivage |
| **Purge données** | Bouton Paramètres — vide SQLite métier, conserve settings |

---

## 14. Critères d'acceptation (MVP → V1)

### MVP (Phase 0–1) ✅

- [x] Déposer un PNG/PDF/HEIC → champs pré-remplis (Gemini, Ollama ou mock).
- [x] Analyse IA produit un JSON multi-tâches valide (Gemini JSON strict + Pydantic).
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

### V1 complète (Phase 4–5) ✅ / 🔄

- [x] Recherche GED (titre + raw_summary + tags).
- [x] Notifications J-3 et J-1 sur Mac (app ouverte).
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
> → Relances automatiques à J-3 et J-1 pour chaque deadline.

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

# Configuration Gemini (copier .env.example → .env)
cp .env.example .env
# Éditer GEMINI_API_KEY=...

# Vérifier Ollama (fallback optionnel)
python scripts/check_ollama.py
ollama pull llama3.2-vision

# Tests
pytest tests/ -q
```

---

**État actuel** : V1 fonctionnelle avec analyse **Gemini** prioritaire, fallback Ollama, Dashboard escamotable, Autopilote, routines récurrentes, purge SQLite et tests isolés. Prochaine étape recommandée : finaliser le README et migrer vers `google.genai` (SDK successor).
