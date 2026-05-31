"""Prompts système pour l'analyse Menu & Drive (Gemini / OpenRouter)."""

from __future__ import annotations

from app.models.drive import DriveMenuInput, MEAL_SLOTS, parse_meal_slot

DRIVE_SYSTEM_PROMPT = """Tu es un chef de famille et expert en batch cooking pour une famille française.
Ta mission : transformer un menu hebdomadaire en (1) un planning batch cooking structuré et (2) une liste de courses détaillée (besoins culinaires précis).

RÉPONDS UNIQUEMENT en JSON valide. Aucun texte avant ou après le JSON. Aucun markdown. Aucun commentaire.
INTERDICTION ABSOLUE : pas de réflexion, pas de commentaire, pas de champ supplémentaire, AUCUN code HTML/CSS.
Le JSON doit contenir EXACTEMENT 2 clés racine : "planning_repas" et "liste_courses".

═══ RÈGLE 1 — planning_repas (data pure, zéro balise HTML) ═══
Génère UNIQUEMENT un objet pour chaque créneau EXPLICITEMENT listé dans « PLATS ENFANTS » du prompt utilisateur.
INTERDICTION ABSOLUE : ne complète pas les créneaux vides, n'invente pas de repas pour les jours non saisis.
Si un seul créneau est saisi (ex. « Mardi soir : épinards hachés »), planning_repas ne contient QU'UNE seule ligne.
Ne fusionne pas les lignes : un objet par créneau saisi.

Chaque objet contient :
- "jour" : EXACTEMENT l'une des valeurs : "Dimanche" | "Lundi" | "Mardi" | "Mercredi" | "Jeudi" | "Vendredi" | "Samedi"
- "moment" : "Midi" ou "Soir" — doit correspondre au créneau saisi (ex. « Mardi soir » → jour "Mardi", moment "Soir")
- "plat" : nom du plat tel que saisi pour ce créneau (tu peux l'enrichir légèrement, ex. « épinards hachés et poisson »)
- "batch_cooking_dimanche" : préparation dimanche (découpe, cuisson, marinade, portionnage, congélation). Optimise Four, Air Fryer et Congélateur.
- "action_minute" : action jour J (réchauffer, assembler, accompagnement frais, cuisson rapide)

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
Ne liste que les ingrédients des plats EXPLICITEMENT saisis + extras + suppléments régime. Pas d'ingrédients pour des repas non saisis.

═══ RÈGLE 3 — Cohérence menu ↔ courses ═══
Couvrir uniquement les plats saisis, respecter le régime quotidien saisi, plats enfants prioritaires.

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


def build_drive_system_prompt() -> str:
    return DRIVE_SYSTEM_PROMPT


def build_drive_user_prompt(payload: DriveMenuInput) -> str:
    semaine_label = payload.semaine_reference.strftime("%d/%m/%Y")
    lines = [
        "Analyse ce menu hebdomadaire et génère le planning batch cooking structuré "
        "(planning_repas en JSON pur, sans HTML) "
        "+ la liste de courses (besoins culinaires en unités standardisées g/kg/ml/L/u).",
        "",
        "═══ DATE DU PLANNING ═══",
        f"Semaine du {semaine_label}",
        "",
        "═══ CONVIVES ENFANTS (plats) ═══",
        f"{payload.nb_convives_enfants} personnes",
        "",
        "═══ CONVIVES RÉGIME / EXTRAS ═══",
        f"{payload.nb_convives_regime} personnes",
        "",
        "═══ PLATS ENFANTS (prioritaires) ═══",
    ]
    for slot, plat in payload.plats.items():
        lines.append(f"{slot} : {plat}")
    if not payload.plats:
        lines.append("(aucun plat enfant saisi)")
    else:
        lines += [
            "",
            "═══ CONTRAINTE CRÉNEAUX (strict) ═══",
            f"{len(payload.plats)} créneau(x) saisi(s) sur {len(MEAL_SLOTS)} — "
            "planning_repas et liste_courses UNIQUEMENT pour ces créneaux.",
        ]
        for slot in payload.plats:
            try:
                jour, moment = parse_meal_slot(slot)
                lines.append(f"  → autoriser : jour={jour!r}, moment={moment!r}")
            except ValueError:
                lines.append(f"  → créneau : {slot!r}")
        lines.append("Ne génère AUCUN autre repas ni ingrédient pour les créneaux non listés ci-dessus.")
    lines += ["", "═══ RÉGIME ADULTE (supplément par jour) ═══"]
    for day, regime in payload.regime.items():
        lines.append(f"{day} : {regime}")
    if not payload.regime:
        lines.append("(aucune contrainte régime saisie)")
    lines += ["", "═══ EXTRAS (hors menu, à ajouter à la liste) ═══"]
    lines.append(payload.extras if payload.extras else "(aucun extra)")
    lines += ["", "JSON strict uniquement — planning_repas + liste_courses, sans HTML."]
    return "\n".join(lines)
