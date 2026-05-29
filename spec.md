# Trankil-v2 — Spécification Technique & Fonctionnelle

> **Version** : 0.2-validated  
> **Date** : 29 mai 2026  
> **Statut** : Validé par l'Architecte — prêt pour implémentation  
> **Dépôt git** : `IA_Personal_Secretaire` · **Nom UI** : **Trankil-v2**

---

## Table des matières

1. [Vision & Principes](#1-vision--principes)
2. [Stack technique & contraintes](#2-stack-technique--contraintes)
3. [Architecture système](#3-architecture-système)
4. [Modèle de données](#4-modèle-de-données)
5. [Vue 1 — Inbox (analyse & validation)](#5-vue-1--inbox-analyse--validation)
6. [Vue 2 — Tableau de bord (Kanban)](#6-vue-2--tableau-de-bord-kanban)
7. [Vue 3 — GED / Archives](#7-vue-3--ged--archives)
8. [Automatisations](#8-automatisations)
9. [Intégration Ollama (IA locale)](#9-intégration-ollama-ia-locale)
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
| **Local-first** | Données, fichiers et analyse IA restent sur la machine. Aucun envoi de documents vers un cloud pour l'analyse. |
| **Souveraineté** | SQLite + filesystem local ; pas de compte obligatoire. |
| **Mac natif** | Notifications macOS, chemin fixe `~/Trankil-v2`. |
| **Itératif** | MVP testable sans Ollama (mode mock), puis enrichissement progressif. |
| **Français V1** | Interface en français uniquement ; pas d'i18n en V1. |

### 1.3 Persona & workflow quotidien (référence UX)

```
[Courrier PDF] ──► Scanner ──┐
[Photo iPhone] ──► HEIC ────┤
[Mail capture] ──► PNG ─────┤──► Drag & Drop ──► Inbox ──► Validation ──► Dashboard + GED
```

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
| IA locale | **Ollama** — modèle vision : `llama3.2-vision` |
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
httpx                    # client Ollama
pydantic>=2.0            # validation JSON IA
python-dateutil          # parsing dates
google-api-python-client # Calendar (phase 4)
google-auth-oauthlib
Pillow                   # preview images
pillow-heif              # support HEIC (photos iPhone)
pdf2image                # PDF → image (requiert Poppler)
pypdf                    # métadonnées PDF (optionnel)
```

### 2.4 Lancement

| Méthode | Usage |
|---------|-------|
| `python main.py` | Développement et Terminal |
| **`start.command`** | Double-clic sur le Bureau — confort quotidien entrepreneur |

Le script `start.command` active le venv, lance l'app et ouvre le navigateur sur `http://localhost:8080`.

---

## 3. Architecture système

### 3.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────┐
│                     NiceGUI (Frontend local)                     │
│   Inbox │ Dashboard (Kanban) │ GED/Archives │ Settings          │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Application Layer (Python)                  │
│  DocumentService │ TaskService │ TagService │ GEDService          │
│  OllamaClient ( + MockOllamaClient ) │ NotificationService       │
│  CalendarSyncService (opt-in, OFF par défaut)                    │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
  SQLite            ~/Trankil-v2/      Ollama :11434
  database.sqlite   Pro|Perso/GED/     llama3.2-vision
                    (chemin fixe V1)
```

### 3.2 Processus applicatif

| Composant | Rôle |
|-----------|------|
| **Main app** | Point d'entrée NiceGUI, routing entre vues, lifecycle |
| **Background scheduler** | Thread daemon : vérifie deadlines, envoie notifications J-3 / J-1 (**app ouverte uniquement en V1**) |
| **Services** | Couche métier découplée de l'UI (testable unitairement) |

### 3.3 Emplacement des données (chemin fixe V1)

| Ressource | Chemin |
|-----------|--------|
| Racine utilisateur | **`~/Trankil-v2/`** (fixe, non configurable en V1) |
| GED Pro | `~/Trankil-v2/Pro/GED/` |
| GED Perso | `~/Trankil-v2/Perso/GED/` |
| Base SQLite | `~/Trankil-v2/database.sqlite` |
| Inbox temporaire | `~/Trankil-v2/.inbox/` (fichiers en attente de validation) |
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
| `document_id` | INTEGER FK NULL | Lien vers `documents.id` (**1 fichier = 1 tâche** en V1) |
| `raw_summary` | TEXT NULL | Résumé IA — indexé pour recherche GED |
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
| `name` | TEXT UNIQUE NOT NULL | Ex: `Tech`, `Expo` (sans `#`) |
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

Clés settings prévues :
- `ollama_model` : `"llama3.2-vision"`
- `ollama_base_url` : `"http://localhost:11434"`
- `google_calendar_auto_sync` : `"false"` (**OFF par défaut**)
- `notification_enabled` : `"true"`

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

### 4.3 Index recommandés

```sql
CREATE INDEX idx_tasks_deadline ON tasks(deadline);
CREATE INDEX idx_tasks_category ON tasks(category);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_documents_stored_path ON documents(stored_path);
CREATE INDEX idx_tasks_raw_summary ON tasks(raw_summary);  -- recherche GED
```

---

## 5. Vue 1 — Inbox (analyse & validation)

### 5.1 Comportement

1. Zone **drag-and-drop** acceptant : `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, **`.heic`** (photos iPhone via `pillow-heif`).
2. À l'upload, copie du fichier dans `~/Trankil-v2/.inbox/{uuid}_{original_name}`.
3. Appel **OllamaClient.analyze_document(path)** → JSON structuré.
4. Affichage **split-view** :
   - **Gauche** : preview document (image directe ; HEIC converti ; PDF → **page 1 uniquement**).
   - **Droite** : formulaire éditable pré-rempli.
5. Bouton **« Valider et Classer »** :
   - Renomme et déplace le fichier vers GED (§7).
   - Crée `documents` + `tasks` (+ `raw_summary`) + tags.
   - Retire de l'inbox temporaire.
   - Propose bouton **« Synchroniser l'agenda »** (manuel, Calendar non auto par défaut).

### 5.2 Schéma JSON attendu de l'IA

```json
{
  "title": "Mettre à jour le SDK Expo avant coupure",
  "date_emission": "2026-05-28",
  "date_event": null,
  "deadline": "2026-06-26",
  "category": "pro",
  "tags": ["Tech", "Expo", "Maintenance"],
  "confidence": 0.85,
  "raw_summary": "Mail Expo indiquant une maintenance obligatoire..."
}
```

### 5.3 Règles de parsing & fallback

| Champ | Règle |
|-------|-------|
| `date_emission` | Extraire du document ; si absent → date du jour (timezone locale Mac) |
| `deadline` | Extraire la **date officielle** telle qu'inscrite sur le document (ex: « avant le 26 juin » → `2026-06-26`). **Pas de marge appliquée en base.** |
| `category` | `pro` par défaut si ambigu ; l'utilisateur corrige |
| `tags` | 1 à 5 tags, capitalisation normalisée |
| `raw_summary` | Texte libre IA ; **persisté en base** pour recherche GED |

### 5.4 Mode mock (sans Ollama)

Si Ollama indisponible ou modèle `llama3.2-vision` absent :
- **Mock uniquement** — pas de modèle de secours (`llava`, etc.) pour éviter les hallucinations de dates.
- Retourner un JSON de démo basé sur le nom/extension du fichier.
- Bandeau UI : « Mode démo — Ollama non disponible ».
- Permet de tester tout le flux Inbox → Dashboard → GED.

### 5.5 Champs formulaire (UI)

| Champ | Widget | Éditable |
|-------|--------|----------|
| Titre / Action | Input text | Oui |
| Date d'émission | Date picker | Oui |
| Date événement | Date picker (optionnel) | Oui |
| Deadline | Date picker | Oui |
| Catégorie | Radio Pro / Perso | Oui |
| Tags | Chips + ajout manuel | Oui |

---

## 6. Vue 2 — Tableau de bord (Kanban)

### 6.1 Filtres globaux (barre supérieure)

| Filtre | Comportement |
|--------|--------------|
| **Tout** | Toutes catégories |
| **Pro uniquement** | `category = 'pro'` |
| **Perso uniquement** | `category = 'perso'` |
| **Méta-tags** | Chips cliquables ; multi-sélection en logique **OR** (union : voir toutes les tâches ayant **au moins un** des tags sélectionnés) |

### 6.2 Colonnes

| Colonne | Contenu | Style |
|---------|---------|-------|
| **EN RETARD / URGENT** | Non archivées, deadline passée ou ≤ 48h | Fond rouge, badge urgence |
| **À FAIRE** | Non archivées, deadline > 48h | Tri deadline ASC |
| ↳ *Sans date* | Non archivées, `deadline IS NULL` | Sous-section en **bas** de la colonne « À FAIRE » |
| **ARCHIVÉ** | `completed_at` renseigné | Vert discret, opacité réduite |

### 6.3 Carte tâche

Affichage minimal :
```
[Pro] Mettre à jour Expo
• Reçu le : 28/05/2026
• Deadline : 26/06/2026
• Tags : #Tech #Expo #Maintenance
☐ Fait    [Modifier]    [📅 Sync Calendar]
```

Interactions :
- **Checkbox « Fait »** → `completed_at = now()`, animation vers Archivé.
- **Bouton « Modifier »** → ouvre formulaire d'édition (titre, dates, catégorie, tags, notes). **Indispensable** : l'IA peut se tromper, les plans changent.
- **Clic document** → ouvre preview ou révèle dans GED.
- **Sync Calendar** → création événement manuelle (§10).

### 6.4 Rafraîchissement

- Recalcul colonne « Urgent » à chaque chargement et toutes les **60 s** (timer NiceGUI).
- Pas de WebSocket externe ; tout local.

---

## 7. Vue 3 — GED / Archives

### 7.1 Convention de nommage

```
{YYYY-MM-DD}_{Slug-Titre}.{ext}
```

Exemples :
- `2026-05-28_Maintenance_Expo_SDK.png`
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

### 8.1 Relances anti-oubli (macOS)

| Déclencheur | Condition | Action |
|-------------|-----------|--------|
| J-3 | `deadline - today == 3 jours`, tâche non archivée, notif pas déjà envoyée | Notification système |
| J-1 | idem à J-1 | Notification + carte dashboard en rouge vif |

Message type :
```
⚠️ Trankil-v2 : Il te reste 3 jours pour « Mettre à jour Expo ».
```

Implémentation V1 :
- Thread daemon au démarrage app, boucle toutes les **30 min**.
- **Uniquement tant que l'application est ouverte.**
- Log dans `notifications_log` pour idempotence.

**V1.1** : daemon `launchd` pour notifications même app fermée.

### 8.2 Google Calendar Sync

Voir §10.

---

## 9. Intégration Ollama (IA locale)

### 9.1 Configuration

```yaml
ollama:
  base_url: http://localhost:11434
  model: llama3.2-vision
  timeout_seconds: 120
```

### 9.2 Flux d'analyse

1. Vérifier disponibilité : `GET /api/tags` + présence de `llama3.2-vision`.
2. Préparer l'image : fichier natif, HEIC → PNG, PDF → **page 1** via `pdf2image` + Poppler.
3. Encoder image en base64 pour l'API Ollama vision.
4. Prompt système structuré demandant **JSON strict** (voir §5.2).
5. Parser réponse avec `pydantic` ; retry 1× si JSON invalide.
6. Si échec ou modèle absent → **MockOllamaClient** (pas d'autre modèle).

### 9.3 Prompt système

```
Tu es un assistant secrétaire pour un entrepreneur français.
Analyse ce document (courrier, facture, capture d'écran d'e-mail, photo).
Extrais les informations et réponds UNIQUEMENT en JSON valide avec les clés :
title, date_emission (ISO), date_event (ISO ou null), deadline (ISO ou null),
category ("pro" ou "perso"), tags (array strings), confidence (0-1), raw_summary.
Dates : format YYYY-MM-DD. Si date absente, date_emission = aujourd'hui.
Pour deadline, extrais la date limite OFFICIELLE telle qu'indiquée sur le document.
Ne modifie pas la date pour ajouter une marge : le système de relance gère les alertes.
raw_summary : résumé textuel du contenu du document pour recherche ultérieure.
```

### 9.4 PDF — Page 1 uniquement (V1)

Conversion page 1 en image (`pdf2image` + **Poppler** via `brew install poppler`) puis envoi à Ollama vision. 90 % des informations critiques (dates, montants) d'un courrier administratif ou d'une facture sont sur la première page.

### 9.5 HEIC — Photos iPhone (V1)

Support natif via **`pillow-heif`** : conversion transparente HEIC → preview + analyse vision.

---

## 10. Intégration Google Calendar

### 10.1 Périmètre V1

- OAuth 2.0 desktop flow (Google Cloud Console).
- Scopes : `https://www.googleapis.com/auth/calendar.events`
- Calendrier cible : **primary**
- **Sync automatique OFF par défaut** — évite de polluer l'agenda avec des scans de test.
- Procédure de configuration Google Cloud documentée dans le **README** ; `credentials.json` configuré ensemble au moment voulu.

### 10.2 Création événement

| Champ Google | Valeur |
|--------------|--------|
| Titre | `[PRO] Mettre à jour Expo (Limite: 26 Juin)` |
| Date | `deadline` en all-day event |
| Description | `Document reçu le 28/05/2026. Tags: #Tech, #Expo.` |

### 10.3 UX

- Bouton **« Synchroniser l'agenda »** sur carte tâche et post-validation Inbox (**action manuelle**).
- Switch global **Settings** : activer sync auto (désactivé par défaut).
- Indicateur visuel si déjà synchronisé.

### 10.4 Hors-ligne

- Si pas de credentials : bouton grisé + lien « Configurer Google Calendar » (renvoie vers README).

---

## 11. Arborescence projet

```
IA_Personal_Secretaire/          # dépôt git
├── spec.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── main.py                      # entrypoint NiceGUI
├── start.command                # double-clic Bureau (copie/install doc)
├── app/
│   ├── __init__.py
│   ├── config.py                # constantes (ROOT_PATH fixe)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── schema.sql
│   │   └── migrations/
│   ├── models/
│   │   ├── task.py
│   │   ├── document.py
│   │   └── tag.py
│   ├── services/
│   │   ├── document_service.py
│   │   ├── task_service.py
│   │   ├── ged_service.py
│   │   ├── ollama_client.py
│   │   ├── mock_ollama_client.py
│   │   ├── notification_service.py
│   │   └── calendar_service.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── layout.py            # nav Trankil-v2, shell
│   │   ├── inbox_view.py
│   │   ├── dashboard_view.py
│   │   ├── ged_view.py
│   │   ├── settings_view.py
│   │   └── task_edit_dialog.py  # modal Modifier
│   └── utils/
│       ├── dates.py
│       ├── slugify.py
│       └── file_preview.py      # PDF p1, HEIC, images
├── scripts/
│   ├── init_db.py
│   └── check_ollama.py
└── tests/
    ├── test_task_status.py
    ├── test_ged_naming.py
    └── test_ollama_mock.py
```

---

## 12. Plan d'implémentation itérative

> **Priorité validée** : Phase 0 + Inbox MVP en premier — valider qu'Ollama lit un screenshot et produit le bon JSON avant le reste.

### Phase 0 — Fondations (Sprint 1) ← **EN COURS**
- [ ] Initialiser dépôt, `pyproject.toml`, `.gitignore`
- [ ] Créer `~/Trankil-v2` au premier lancement
- [ ] Schéma SQLite + migrations
- [ ] `OllamaClient` + `MockOllamaClient`
- [ ] Tests unitaires statut tâche + slug GED
- [ ] `start.command`

### Phase 1 — Inbox MVP (Sprint 2) ← **PRIORITÉ IMMÉDIATE**
- [ ] Drag & drop NiceGUI (PDF, PNG, JPG, HEIC)
- [ ] Preview document (PDF p1, HEIC, images)
- [ ] Analyse Ollama vision (ou mock) → formulaire JSON
- [ ] Validation → GED + task + raw_summary en base

### Phase 2 — Dashboard (Sprint 3)
- [ ] Kanban 3 colonnes + sous-section « Sans date »
- [ ] Filtres Pro/Perso + tags (OR)
- [ ] Checkbox archivage + bouton **Modifier**

### Phase 3 — GED / Archives (Sprint 4)
- [ ] Recherche full-text (incl. raw_summary)
- [ ] Preview & ouverture Finder

### Phase 4 — Automatisations (Sprint 5)
- [ ] Notifications J-3 / J-1 (app ouverte)
- [ ] Google Calendar OAuth + sync manuelle

### Phase 5 — Polish (Sprint 6)
- [ ] Settings UI (sync auto Calendar, notifications)
- [ ] Gestion erreurs, logs
- [ ] README : Ollama, Poppler, HEIC, Google Calendar, `start.command`

### Backlog V1.1+
- [ ] Daemon `launchd` pour notifications app fermée
- [ ] Export backup zip `~/Trankil-v2`
- [ ] Chemin racine configurable

---

## 13. Décisions validées (arbitrages Architecte)

| Domaine | Décision |
|---------|----------|
| **Nom UI** | **Trankil-v2** (dépôt git : `IA_Personal_Secretaire`) |
| **Langue** | Français uniquement V1, pas d'i18n |
| **UI framework** | **NiceGUI** validé à 100 % |
| **Filtre tags** | **OR** (union) |
| **Sans deadline** | Colonne « À FAIRE », sous-section **« Sans date »** en bas |
| **Édition tâche** | **Oui** — bouton « Modifier » sur chaque carte |
| **Fichiers / tâche** | **1 = 1** en V1 |
| **Chemin racine** | **`~/Trankil-v2` fixe** V1 |
| **PDF** | **Page 1** uniquement V1 |
| **Poppler** | Prérequis Homebrew, documenté README |
| **Lancement** | `python main.py` + **`start.command`** sur le Bureau |
| **Modèle secours** | **Mock uniquement** (pas de llava) |
| **raw_summary** | **Stocké en base**, indexé pour recherche GED |
| **Deadline en base** | **Date officielle** du document ; marge = relances J-3/J-1 |
| **Google Calendar** | **OFF par défaut**, bouton manuel ; procédure README |
| **Notifications V1** | **App ouverte uniquement** ; launchd en V1.1 |
| **HEIC** | **Oui V1** via `pillow-heif` |
| **Backup zip** | Plus tard (Time Machine suffit) |
| **Priorisation** | Phase 0 → **Inbox MVP** → Dashboard → GED → Automatisations |

---

## 14. Critères d'acceptation (MVP → V1)

### MVP (fin Phase 0–1) — objectif immédiat

- [ ] Déposer un PNG/PDF/HEIC dans Inbox → champs pré-remplis (Ollama ou mock).
- [ ] Ollama vision lit un screenshot et produit un JSON structuré valide.
- [ ] Modifier et valider → fichier dans `Pro/GED/` ou `Perso/GED/` avec bon nommage.
- [ ] `raw_summary` persisté et searchable.

### MVP étendu (fin Phase 2)

- [ ] Tâche visible dans Dashboard, bonne colonne selon deadline.
- [ ] Tâches sans deadline en sous-section « Sans date ».
- [ ] Cocher « Fait » → Archivé.
- [ ] Filtrer Pro / Perso / tags (OR).
- [ ] Bouton « Modifier » fonctionnel.

### V1 complète (fin Phase 4–5)

- [ ] Recherche GED < 1 s sur 100+ documents (titre + raw_summary + tags).
- [ ] Notifications J-3 et J-1 sur Mac (app ouverte).
- [ ] Sync Google Calendar manuelle + option auto (OFF par défaut).
- [ ] README complet : Ollama, Poppler, pillow-heif, Google Calendar, `start.command`.

---

## Annexe A — Exemple document type

> Courrier URSSAF : « Paiement cotisations avant le 15/06/2026 »  
> → Catégorie Pro, tags Compta URSSAF, **deadline `2026-06-15`** (date officielle), émission = date du courrier scanné.  
> → Relances automatiques à J-3 (12/06) et J-1 (14/06).

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

# Vérifier Ollama
python scripts/check_ollama.py
ollama pull llama3.2-vision
```

---

**Prochaine étape** : démarrage **Phase 0** (fondations) puis **Phase 1** (Inbox MVP).
