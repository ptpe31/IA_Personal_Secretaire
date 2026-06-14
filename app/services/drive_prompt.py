"""Prompts système pour l'analyse Menu & Drive (Gemini / OpenRouter)."""

from __future__ import annotations

from app.models.drive import (
    DriveMenuInput,
    MEAL_SLOTS,
    has_enfants_consignes,
    has_regime_consignes,
    ordered_meal_slots,
    ordered_regime_days,
    ordered_week_days,
    parse_meal_slot,
)

DRIVE_SYSTEM_PROMPT_BASE = """Tu es un chef de famille et expert en batch cooking pour une famille française.
Ta mission : transformer un menu hebdomadaire en (1) un planning batch cooking structuré et (2) une liste de courses détaillée (besoins culinaires précis).

RÉPONDS UNIQUEMENT en JSON valide. Aucun texte avant ou après le JSON. Aucun markdown. Aucun commentaire.
INTERDICTION ABSOLUE : pas de réflexion, pas de commentaire, pas de champ supplémentaire, AUCUN code HTML/CSS.
Le JSON doit contenir EXACTEMENT 2 clés racine : "planning_repas" et "liste_courses".

═══ RÈGLE 1 — planning_repas (data pure, zéro balise HTML) ═══
Chaque objet contient :
- "jour" : EXACTEMENT l'une des valeurs : "Dimanche" | "Lundi" | "Mardi" | "Mercredi" | "Jeudi" | "Vendredi" | "Samedi"
- "moment" : "Midi" ou "Soir" — doit correspondre au créneau (ex. « Mardi soir » → jour "Mardi", moment "Soir")
- "plat" : nom du plat pour ce créneau
- "batch_cooking_dimanche" : préparation dimanche (découpe, cuisson, marinade, portionnage, congélation). Optimise Four, Air Fryer et Congélateur.
- "action_minute" : action jour J (réchauffer, assembler, accompagnement frais, cuisson rapide)

Chronologie : respecte l'ordre des jours indiqué dans « CHRONOLOGIE DE LA SEMAINE » du prompt utilisateur (premier jour → fin de semaine). Le batch cooking doit suivre cette progression.

Si un plat est identique sur plusieurs jours, répète une ligne par créneau (ne fusionne pas).

═══ RÈGLE 2 — liste_courses (besoin culinaire strict) ═══
Un objet par ingrédient/produit à acheter :

- "mot_cle" : Identifiant court stable (**3 mots maximum**, minuscules, sans article). Ex: "lait entier", "pomme de terre", "essuie-tout"
- "libelle" : Description pour l'humain (**3 mots maximum**, nature/découpe). Ex: "lait entier UHT", "pommes de terre", "essuie-tout triple"
- "rayon" : UNE des 5 valeurs EXACTES : "Épicerie" | "Frais" | "Fruits & Légumes" | "Bébé" | "Entretien"
- "quantite_recette" : Quantité numérique brute nécessaire pour toute la semaine (décimal autorisé). Ex: 3.0, 1200.0, 12.0
- "unite_recette" : Unité STRICTEMENT parmi : "g" | "kg" | "ml" | "L" | "u"
  → "g" ou "kg" : solides et matières grasses (farine, pommes de terre, beurre, jambon)
  → "ml" ou "L" : liquides (lait, crème, huile)
  → "u" : produits comptables indivisibles (œufs, couches, essuie-tout, boîtes)

INTERDICTION ABSOLUE : ne calcule PAS le nombre de paquets, boîtes ou bouteilles à acheter. Fournis uniquement le besoin culinaire total. Le logiciel fera la règle de trois avec le conditionnement magasin.

Exemples :
- 3 L de lait pour la semaine → quantite_recette: 3, unite_recette: "L"
- 1,2 kg de pommes de terre → quantite_recette: 1.2, unite_recette: "kg"
- 12 œufs → quantite_recette: 12, unite_recette: "u"
- 200 g de jambon → quantite_recette: 200, unite_recette: "g"

Règles quantités : adapter aux convives enfants et convives régime/extras (base 4 chacun), fusionner doublons (même mot_cle + même unite_recette), inclure extras, exclure sel/poivre/huile/eau sauf si demandé.

═══ RÈGLE 3 — Cohérence menu ↔ courses ═══
Couvrir uniquement les plats des créneaux autorisés, respecter le régime quotidien saisi ou généré, plats enfants prioritaires.

═══ RÈGLE 4 — JSON strict ═══
Pas de trailing comma. Pas de champs supplémentaires. Pas de HTML.

Structure JSON STRICTE :
{
  "planning_repas": [{
    "jour": "Lundi",
    "moment": "Midi",
    "plat": "Colombo de poulet",
    "batch_cooking_dimanche": "Découper les blancs, mariner dans les épices",
    "action_minute": "Cuire à l'Air Fryer 15 min, réchauffer la sauce"
  }],
  "liste_courses": [{
    "mot_cle": "lait entier",
    "libelle": "lait entier UHT",
    "rayon": "Frais",
    "quantite_recette": 3,
    "unite_recette": "L"
  }]
}"""

DRIVE_SYSTEM_PROMPT_MANUAL_SLOTS = """
═══ RÈGLE 1a — Mode saisie manuelle (créneaux explicites) ═══
Génère UNIQUEMENT un objet pour chaque créneau EXPLICITEMENT listé dans « PLATS ENFANTS » du prompt utilisateur.
INTERDICTION ABSOLUE : ne complète pas les créneaux vides, n'invente pas de repas pour les jours non saisis.
Ne fusionne pas les lignes : un objet par créneau saisi.
Ne liste que les ingrédients des plats EXPLICITEMENT saisis + extras + suppléments régime."""

DRIVE_SYSTEM_PROMPT_CONSIGNES = """
═══ RÈGLE 1b — Mode consignes IA (créneaux cibles) ═══
Pour chaque créneau listé dans « CRÉNEAUX À GÉNÉRER (consignes IA) », invente un plat adapté aux consignes enfants, au nombre de convives et à la chronologie de la semaine.
Respecte strictement les contraintes alimentaires des consignes (allergies, interdits, préférences).
Les créneaux déjà renseignés manuellement dans « PLATS ENFANTS » sont prioritaires : reprends-les tels quels, ne les remplace pas.
Génère planning_repas et ingrédients UNIQUEMENT pour les créneaux autorisés (manuels + cibles consignes).
Ne génère AUCUN repas hors de cette liste."""

DRIVE_SYSTEM_PROMPT_REGIME_CONSIGNES = """
═══ RÈGLE 3b — Régime par consignes IA ═══
Pour chaque jour listé dans « JOURS RÉGIME À GÉNÉRER », déduis la contrainte régime adulte quotidienne à partir des consignes régime.
Intègre les suppléments ou substitutions régime dans liste_courses (ex. alternatives sans lactose, protéines spécifiques).
Les jours déjà renseignés manuellement dans « RÉGIME ADULTE » sont prioritaires."""


def build_drive_system_prompt(payload: DriveMenuInput | None = None) -> str:
    parts = [DRIVE_SYSTEM_PROMPT_BASE]
    if payload is not None and has_enfants_consignes(payload):
        parts.append(DRIVE_SYSTEM_PROMPT_CONSIGNES)
    else:
        parts.append(DRIVE_SYSTEM_PROMPT_MANUAL_SLOTS)
    if payload is not None and has_regime_consignes(payload):
        parts.append(DRIVE_SYSTEM_PROMPT_REGIME_CONSIGNES)
    return "\n".join(parts)


def build_drive_user_prompt(payload: DriveMenuInput) -> str:
    semaine_label = payload.semaine_reference.strftime("%d/%m/%Y")
    premier_jour = payload.premier_jour_semaine
    week_days = ordered_week_days(premier_jour)
    slot_order = ordered_meal_slots(premier_jour)
    regime_order = ordered_regime_days(premier_jour)
    manual_slots = set(payload.plats.keys())
    consignes_targets = [
        slot for slot in payload.enfants_creneaux_cibles if slot not in manual_slots
    ]
    manual_regime_days = set(payload.regime.keys())
    regime_targets = [
        day for day in payload.regime_jours_cibles if day not in manual_regime_days
    ]

    lines = [
        "Analyse ce menu hebdomadaire et génère le planning batch cooking structuré "
        "(planning_repas en JSON pur, sans HTML) "
        "+ la liste de courses (besoins culinaires en unités standardisées g/kg/ml/L/u).",
        "",
        "═══ DATE DU PLANNING ═══",
        f"Semaine du {semaine_label}",
        "",
        "═══ CHRONOLOGIE DE LA SEMAINE ═══",
        f"Premier jour de la semaine : {premier_jour}",
        f"Ordre des jours à respecter : {' → '.join(week_days)}",
        "Présente le batch cooking et les actions minute en suivant cette chronologie.",
        "",
        "═══ CONVIVES ENFANTS (plats) ═══",
        f"{payload.nb_convives_enfants} personnes",
        "",
        "═══ CONVIVES RÉGIME / EXTRAS ═══",
        f"{payload.nb_convives_regime} personnes",
        "",
        "═══ PLATS ENFANTS (prioritaires) ═══",
    ]
    for slot in slot_order:
        if slot in payload.plats:
            lines.append(f"{slot} : {payload.plats[slot]}")
    if not payload.plats:
        lines.append("(aucun plat enfant saisi manuellement)")

    if has_enfants_consignes(payload):
        lines += [
            "",
            "═══ CONSIGNES ENFANTS (IA) ═══",
            payload.enfants_consignes,
            "",
            "═══ CRÉNEAUX À GÉNÉRER (consignes IA) ═══",
        ]
        for slot in consignes_targets:
            lines.append(f"  → {slot}")
        if not consignes_targets:
            lines.append("(tous les créneaux cochés sont déjà renseignés manuellement)")

    allowed_count = len(payload.plats) + len(consignes_targets)
    if allowed_count:
        lines += [
            "",
            "═══ CONTRAINTE CRÉNEAUX (strict) ═══",
            f"{allowed_count} créneau(x) autorisé(s) sur {len(MEAL_SLOTS)} — "
            "planning_repas et liste_courses UNIQUEMENT pour ces créneaux.",
        ]
        for slot in slot_order:
            if slot not in payload.plats and slot not in consignes_targets:
                continue
            try:
                jour, moment = parse_meal_slot(slot)
                lines.append(f"  → autoriser : jour={jour!r}, moment={moment!r}")
            except ValueError:
                lines.append(f"  → créneau : {slot!r}")
        lines.append("Ne génère AUCUN autre repas ni ingrédient pour les créneaux non listés ci-dessus.")
    elif not has_enfants_consignes(payload):
        lines.append("(aucun créneau repas — extras seuls si fournis)")

    lines += ["", "═══ RÉGIME ADULTE (supplément par jour) ═══"]
    for day in regime_order:
        if day in payload.regime:
            lines.append(f"{day} : {payload.regime[day]}")
    if not payload.regime:
        lines.append("(aucune contrainte régime saisie manuellement)")

    if has_regime_consignes(payload):
        lines += [
            "",
            "═══ CONSIGNES RÉGIME (IA) ═══",
            payload.regime_consignes,
            "",
            "═══ JOURS RÉGIME À GÉNÉRER (consignes IA) ═══",
        ]
        for day in regime_targets:
            lines.append(f"  → {day}")
        if not regime_targets:
            lines.append("(tous les jours cochés sont déjà renseignés manuellement)")

    lines += ["", "═══ EXTRAS (hors menu, à ajouter à la liste) ═══"]
    lines.append(payload.extras if payload.extras else "(aucun extra)")
    lines += ["", "JSON strict uniquement — planning_repas + liste_courses, sans HTML."]
    return "\n".join(lines)
