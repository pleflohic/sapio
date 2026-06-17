# SPDX-License-Identifier: AGPL-3.0-or-later
"""Étape (b) : expansion graduée des objets de cours en cartes de restitution.

La politique de graduation (quelles facettes produire selon l'importance) vit
ici, dans du code transparent et réglable, plutôt que dans le modèle. Voir
spec_sapio.md §4. Une carte n'est émise que si son contenu de référence
(`attendu`) existe réellement dans l'objet.
"""

from __future__ import annotations

import re
from collections import Counter

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


# Capture le préfixe numérique d'un libellé : « 1. Conditionnement » → « 1 »,
# « 1.2 Définition » → « 1.2 », « §6.3 Espérance » → « 6.3 ». On tolère un
# préambule non chiffré (« Chapitre », « § ») avant le numéro.
_NUM_RE = re.compile(r"\D*?(\d+(?:[.\-]\d+)*)")


def _num_key(label: str) -> str | None:
    m = _NUM_RE.match(label or "")
    return m.group(1).replace("-", ".") if m else None  # 1-2 et 1.2 → même clé


def _canon_map(labels: list[str]) -> dict[str, str]:
    """{libellé original -> libellé canonique} pour un ensemble de libellés.

    Les libellés qui partagent le même préfixe numérique sont fusionnés sous la
    variante la plus fréquente du groupe. Un libellé sans numéro n'est pas touché.
    """
    groups: dict[str, list[str]] = {}
    for lab in labels:
        k = _num_key(lab)
        if k is not None:
            groups.setdefault(k, []).append(lab)
    mapping: dict[str, str] = {}
    for variants in groups.values():
        canon = Counter(variants).most_common(1)[0][0]
        for v in set(variants):
            mapping[v] = canon
    return mapping


def canonicalize_labels(objects: list[CourseObject]) -> list[CourseObject]:
    """Uniformise chapitre/leçon entre les lots (mutation en place).

    Un même chapitre ou une même section peut être étiqueté légèrement
    différemment d'un appel LLM à l'autre (« 1.2 Définition et unicité » vs
    « 1.2 Définition, unicité »), ce qui créerait deux decks pour une seule
    section sur les jointures de lots. On regroupe par préfixe numérique et on
    retient le libellé le plus fréquent. Sans numérotation, rien n'est modifié.
    """
    chap_map = _canon_map([o.chapitre for o in objects])
    for o in objects:
        o.chapitre = chap_map.get(o.chapitre, o.chapitre)
    # Leçons canonisées DANS chaque chapitre canonique : un même numéro de
    # section ne se répète pas d'un chapitre à l'autre, mais on cloisonne par
    # sécurité (« 2.1 » du chapitre 2 ne doit pas fusionner avec un autre).
    by_chap: dict[str, list[str]] = {}
    for o in objects:
        by_chap.setdefault(o.chapitre, []).append(o.lecon)
    lec_map: dict[tuple[str, str], str] = {}
    for chap, lecons in by_chap.items():
        for orig, canon in _canon_map(lecons).items():
            lec_map[(chap, orig)] = canon
    for o in objects:
        o.lecon = lec_map.get((o.chapitre, o.lecon), o.lecon)
    return objects


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
