"""Prompts système pour l'analyse Menu & Drive (Gemini / OpenRouter)."""

from __future__ import annotations

from app.models.drive import (
    DriveMenuInput,
    MEAL_SLOTS,
    has_enfants_consignes,
    has_regime_consignes,
    has_regime_content,
    ordered_meal_slots,
    ordered_week_days,
    parse_meal_slot,
)

DRIVE_SYSTEM_PROMPT_BASE = """Tu es un chef de famille et expert en batch cooking pour une famille française.
Ta mission : transformer un menu hebdomadaire en (1) un planning batch cooking structuré pour les enfants, (2) un planning distinct pour l'hôte au régime spécial, et (3) une liste de courses détaillée (besoins culinaires précis).

RÉPONDS UNIQUEMENT en JSON valide. Aucun texte avant ou après le JSON. Aucun markdown. Aucun commentaire.
INTERDICTION ABSOLUE : pas de réflexion, pas de commentaire, pas de champ supplémentaire, AUCUN code HTML/CSS.
Le JSON doit contenir EXACTEMENT 3 clés racine : "planning_repas", "planning_regime" et "liste_courses".

═══ RÈGLE 1 — planning_repas (plats ENFANTS, data pure, zéro balise HTML) ═══
Chaque objet contient :
- "jour" : EXACTEMENT l'une des valeurs : "Dimanche" | "Lundi" | "Mardi" | "Mercredi" | "Jeudi" | "Vendredi" | "Samedi"
- "moment" : "Midi" ou "Soir" — doit correspondre au créneau (ex. « Mardi soir » → jour "Mardi", moment "Soir")
- "plat" : nom du plat ENFANT pour ce créneau (attractif pour les enfants)
- "batch_cooking_dimanche" : préparation dimanche (découpe, cuisson, marinade, portionnage, congélation). Optimise Four, Air Fryer et Congélateur.
- "action_minute" : action jour J (réchauffer, assembler, accompagnement frais, cuisson rapide)

Si aucun créneau enfant n'est actif, renvoie "planning_repas": [].

═══ RÈGLE 1c — planning_regime (plats HÔTE RÉGIME SPÉCIAL, distincts des enfants) ═══
Même structure que planning_repas. Chaque objet = un plat pour l'hôte additionnel au régime spécial sur un créneau autorisé.
Les plats régime doivent être DIFFÉRENTS des plats enfants et respecter les contraintes régime (allergies, anti-constipation, sans lactose, etc.).
Inclure batch_cooking_dimanche et action_minute pour chaque plat régime.
Si aucun créneau régime n'est actif, renvoie "planning_regime": [].

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

Règles quantités : adapter aux convives enfants (planning_repas) et convives hôte régime (planning_regime), fusionner doublons (même mot_cle + même unite_recette), inclure extras, exclure sel/poivre/huile/eau sauf si demandé.

═══ RÈGLE 3 — Cohérence menu ↔ courses ═══
Couvrir les plats des créneaux autorisés enfants ET hôte régime. Les deux flux sont indépendants mais leurs ingrédients fusionnent dans liste_courses.

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
  "planning_regime": [{
    "jour": "Lundi",
    "moment": "Midi",
    "plat": "Salade verte, haricots verts",
    "batch_cooking_dimanche": "Cuire et portionner les haricots",
    "action_minute": "Assembler la salade"
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
═══ RÈGLE 1a — Mode saisie manuelle ENFANTS (créneaux explicites) ═══
Génère UNIQUEMENT un objet planning_repas pour chaque créneau EXPLICITEMENT listé dans « PLATS ENFANTS » du prompt utilisateur.
INTERDICTION ABSOLUE : ne complète pas les créneaux vides, n'invente pas de repas pour les jours non saisis.
Ne fusionne pas les lignes : un objet par créneau saisi."""

DRIVE_SYSTEM_PROMPT_CONSIGNES = """
═══ RÈGLE 1b — Mode consignes IA ENFANTS (créneaux cibles) ═══
Pour chaque créneau listé dans « CRÉNEAUX ENFANTS À GÉNÉRER (consignes IA) », invente un plat ENFANT attractif, adapté aux consignes, au nombre de convives et à la chronologie de la semaine.
Respecte strictement les contraintes alimentaires des consignes (allergies, interdits, préférences).
Les créneaux déjà renseignés manuellement dans « PLATS ENFANTS » sont prioritaires : reprends-les tels quels, ne les remplace pas.
Génère planning_repas UNIQUEMENT pour les créneaux autorisés (manuels + cibles consignes).
Ne génère AUCUN repas enfant hors de cette liste."""

DRIVE_SYSTEM_PROMPT_REGIME_MANUAL = """
═══ RÈGLE 1d — Mode saisie manuelle HÔTE RÉGIME (créneaux explicites) ═══
Génère UNIQUEMENT un objet planning_regime pour chaque créneau EXPLICITEMENT listé dans « PLATS HÔTE RÉGIME ».
Chaque plat régime doit être distinct des plats enfants du même créneau et respecter les contraintes saisies.
Ne complète pas les créneaux vides."""

DRIVE_SYSTEM_PROMPT_REGIME_CONSIGNES = """
═══ RÈGLE 1e — Mode consignes IA HÔTE RÉGIME (créneaux cibles) ═══
Pour chaque créneau listé dans « CRÉNEAUX RÉGIME À GÉNÉRER (consignes IA) », invente un plat DISTINCT pour l'hôte au régime spécial, adapté aux consignes régime (ex. anti-constipation, sans lactose).
Inclure batch_cooking_dimanche et action_minute pour chaque plat régime.
Les créneaux déjà renseignés manuellement dans « PLATS HÔTE RÉGIME » sont prioritaires.
Génère planning_regime UNIQUEMENT pour les créneaux autorisés (manuels + cibles consignes).
Intègre les ingrédients régime dans liste_courses (quantités pour convives hôte régime)."""


def build_drive_system_prompt(payload: DriveMenuInput | None = None) -> str:
    parts = [DRIVE_SYSTEM_PROMPT_BASE]
    if payload is not None and has_enfants_consignes(payload):
        parts.append(DRIVE_SYSTEM_PROMPT_CONSIGNES)
    else:
        parts.append(DRIVE_SYSTEM_PROMPT_MANUAL_SLOTS)
    if payload is not None and has_regime_consignes(payload):
        parts.append(DRIVE_SYSTEM_PROMPT_REGIME_CONSIGNES)
    elif payload is not None and payload.regime_plats:
        parts.append(DRIVE_SYSTEM_PROMPT_REGIME_MANUAL)
    return "\n".join(parts)


def _append_slot_constraints(
    lines: list[str],
    *,
    slot_order: tuple[str, ...],
    manual_keys: set[str],
    consignes_targets: list[str],
    label: str,
) -> None:
    allowed_count = len(manual_keys) + len(consignes_targets)
    if not allowed_count:
        return
    lines += [
        "",
        f"═══ CONTRAINTE CRÉNEAUX {label} (strict) ═══",
        f"{allowed_count} créneau(x) autorisé(s) sur {len(MEAL_SLOTS)}.",
    ]
    for slot in slot_order:
        if slot not in manual_keys and slot not in consignes_targets:
            continue
        try:
            jour, moment = parse_meal_slot(slot)
            lines.append(f"  → autoriser : jour={jour!r}, moment={moment!r}")
        except ValueError:
            lines.append(f"  → créneau : {slot!r}")


def build_drive_user_prompt(payload: DriveMenuInput) -> str:
    semaine_label = payload.semaine_reference.strftime("%d/%m/%Y")
    premier_jour = payload.premier_jour_semaine
    week_days = ordered_week_days(premier_jour)
    slot_order = ordered_meal_slots(premier_jour)
    manual_slots = set(payload.plats.keys())
    consignes_targets = [
        slot for slot in payload.enfants_creneaux_cibles if slot not in manual_slots
    ]
    manual_regime_slots = set(payload.regime_plats.keys())
    regime_targets = [
        slot for slot in payload.regime_creneaux_cibles if slot not in manual_regime_slots
    ]

    lines = [
        "Analyse ce menu hebdomadaire et génère le planning batch cooking structuré "
        "(planning_repas + planning_regime en JSON pur, sans HTML) "
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
        "═══ CONVIVES HÔTE RÉGIME SPÉCIAL ═══",
        f"{payload.nb_convives_regime} personne(s) — menu distinct des enfants",
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
            "═══ CRÉNEAUX ENFANTS À GÉNÉRER (consignes IA) ═══",
        ]
        for slot in consignes_targets:
            lines.append(f"  → {slot}")
        if not consignes_targets:
            lines.append("(tous les créneaux cochés sont déjà renseignés manuellement)")

    _append_slot_constraints(
        lines,
        slot_order=slot_order,
        manual_keys=manual_slots,
        consignes_targets=consignes_targets,
        label="ENFANTS",
    )

    lines += ["", "═══ PLATS HÔTE RÉGIME (prioritaires) ═══"]
    for slot in slot_order:
        if slot in payload.regime_plats:
            lines.append(f"{slot} : {payload.regime_plats[slot]}")
    if not payload.regime_plats:
        lines.append("(aucun plat hôte régime saisi manuellement)")

    if has_regime_consignes(payload):
        lines += [
            "",
            "═══ CONSIGNES HÔTE RÉGIME (IA) ═══",
            payload.regime_consignes,
            "",
            "═══ CRÉNEAUX RÉGIME À GÉNÉRER (consignes IA) ═══",
        ]
        for slot in regime_targets:
            lines.append(f"  → {slot}")
        if not regime_targets:
            lines.append("(tous les créneaux cochés sont déjà renseignés manuellement)")

    if has_regime_content(payload):
        _append_slot_constraints(
            lines,
            slot_order=slot_order,
            manual_keys=manual_regime_slots,
            consignes_targets=regime_targets,
            label="HÔTE RÉGIME",
        )

    lines += ["", "═══ EXTRAS (hors menu, à ajouter à la liste) ═══"]
    lines.append(payload.extras if payload.extras else "(aucun extra)")
    lines += [
        "",
        "JSON strict uniquement — planning_repas + planning_regime + liste_courses, sans HTML.",
    ]
    return "\n".join(lines)
