# SPDX-License-Identifier: AGPL-3.0-or-later
"""Étape (b) : expansion graduée des objets de cours en cartes de restitution.

La politique de graduation (quelles facettes produire selon l'importance) vit
ici, dans du code transparent et réglable, plutôt que dans le modèle. Voir
spec_sapio.md §4. Une carte n'est émise que si son contenu de référence
(`attendu`) existe réellement dans l'objet.
"""

from __future__ import annotations

from .models import Card, CourseObject, Importance, ObjectType

# Facettes candidates par (catégorie d'objet, importance). L'ordre est l'ordre
# de génération. Une facette n'est gardée que si le champ source est non vide.
_THEOREME_FACETTES = {
    Importance.central: ["enoncer", "reformuler", "preuve", "idees_cles"],
    Importance.standard: ["enoncer", "preuve", "idees_cles"],
    Importance.technique: ["enoncer", "preuve"],
}
_DEFINITION_FACETTES = {
    Importance.central: ["enoncer", "reformuler", "exemple", "contre_exemple"],
    Importance.standard: ["enoncer", "exemple"],
    Importance.technique: ["enoncer"],
}
_EXERCICE_FACETTES = {
    Importance.central: ["resoudre", "idees_cles"],
    Importance.standard: ["resoudre"],
    Importance.technique: ["resoudre"],
}

# Modes qui OPÈRENT sur l'énoncé → on affiche l'énoncé comme contexte.
# (Pas `enoncer` : l'énoncé y est la réponse. Pas `resoudre` : déjà dans la consigne.)
_CONTEXT_MODES = {"reformuler", "preuve", "idees_cles", "exemple", "contre_exemple"}

# Champ de l'objet servant d'`attendu` pour chaque mode.
_ATTENDU_FIELD = {
    "enoncer": "enonce",
    "reformuler": "enonce",
    "preuve": "preuve",
    "idees_cles": "idees_cles",
    "exemple": "exemple",
    "contre_exemple": "contre_exemple",
    "resoudre": "preuve",  # le corrigé de l'exercice
}


def _consigne(mode: str, obj: CourseObject) -> str:
    t = obj.titre
    return {
        "enoncer": f"Énonce précisément : {t}.",
        "reformuler": f"Reformule avec tes propres mots, sans réciter : {t}. Qu'est-ce que ça dit, moralement ?",
        "preuve": f"Démontre : {t}.",
        "idees_cles": f"Quelles sont les idées clés de la preuve / résolution de : {t} ?",
        "exemple": f"Donne et justifie un exemple canonique pour : {t}.",
        "contre_exemple": f"Donne et justifie un contre-exemple éclairant pour : {t}.",
        "resoudre": f"Résous l'exercice : {t}.\n{obj.enonce}",
    }[mode]


def expand(obj: CourseObject) -> list[Card]:
    """Développe un objet de cours en cartes selon la politique graduée."""
    if obj.type is ObjectType.definition:
        facettes = _DEFINITION_FACETTES[obj.importance]
    elif obj.type is ObjectType.exercice:
        facettes = _EXERCICE_FACETTES[obj.importance]
    else:  # theoreme, proposition ou lemme
        facettes = _THEOREME_FACETTES[obj.importance]

    cards: list[Card] = []
    for mode in facettes:
        attendu = getattr(obj, _ATTENDU_FIELD[mode]).strip()
        if not attendu:
            continue  # pas de contenu de référence → pas de carte
        cards.append(
            Card(
                mode=mode,
                type=obj.type.value,
                chapitre=obj.chapitre,
                lecon=obj.lecon,
                titre=obj.titre,
                source_ref=obj.source_ref,
                importance=obj.importance.value,
                consigne=_consigne(mode, obj),
                contexte=obj.enonce if mode in _CONTEXT_MODES else "",
                attendu=attendu,
            )
        )
    return cards


def expand_all(objects: list[CourseObject]) -> list[Card]:
    cards: list[Card] = []
    for obj in objects:
        cards.extend(expand(obj))
    return cards


def _clean(s: str) -> str:
    # "::" est le séparateur de decks Anki — on l'évite dans un libellé.
    return (s or "").strip().replace("::", ":") or "Divers"


def default_deck_map(cards: list[Card]) -> list[dict]:
    """Mapping éditable (chapitre, leçon) → chemin de deck, dérivé des cartes.

    Chemin par défaut = « <chapitre>::<leçon> » (un sous-deck par partie).
    L'utilisateur édite le champ `deck` (renommer, ou même valeur pour fusionner).
    """
    seen: dict[tuple[str, str], dict] = {}
    for c in cards:
        key = (c.chapitre, c.lecon)
        if key in seen:
            continue
        chap, lec = _clean(c.chapitre), _clean(c.lecon)
        deck = f"{chap}::{lec}" if c.chapitre else lec
        seen[key] = {"chapitre": c.chapitre, "lecon": c.lecon, "deck": deck}
    return list(seen.values())


def deck_lookup(deck_map: list[dict]) -> dict[tuple[str, str], str]:
    """Construit le dict (chapitre, leçon) → chemin de deck depuis un mapping."""
    return {(e.get("chapitre", ""), e.get("lecon", "")): e["deck"] for e in deck_map}
