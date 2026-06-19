# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accès à Anki via la librairie Python `anki` (collection ouverte en direct).

Pas d'interface graphique, pas d'AnkiConnect : Sapio ouvre le fichier de
collection `.anki2`, planifie avec FSRS et synchronise avec AnkiWeb. Voir
spec_sapio.md §2. Une seule collection ouverte à la fois (verrou de fichier) :
ne pas lancer Anki desktop sur la même collection en parallèle.

L'interface (find_cards, cards_info, answer_card, ensure_model, card_to_note…)
est conservée pour que le reste de Sapio ne change pas.
"""

from __future__ import annotations

import os
import re
import threading

MODEL_NAME = "Sapio Restitution"
FIELDS = ["Consigne", "Attendu", "Type", "Mode", "Importance", "Titre", "Chapitre", "Lecon", "SourceRef", "Contexte"]

TYPE_LABEL = {
    "definition": "Définition",
    "theoreme": "Théorème",
    "proposition": "Proposition",
    "lemme": "Lemme",
    "exercice": "Exercice",
}

_CSS = """\
.card { font-family: Georgia, serif; font-size: 18px; text-align: left;
        color: #1a1a1a; background: #faf8f3; padding: 1.2em; line-height: 1.5; }
.mode { font-variant: small-caps; letter-spacing: .05em; color: #9a3b2e; font-size: .8em; }
.consigne { margin-top: .4em; font-weight: bold; }
.contexte { margin-top: .6em; padding: .5em .7em; background: #f0ece2; border-radius: 6px; font-size: .92em; }
.attendu { margin-top: .6em; }
.src { margin-top: 1em; font-size: .75em; color: #888; }
hr { border: none; border-top: 1px solid #ddd; margin: 1em 0; }
"""

_FRONT = (
    '<div class="mode"><b>{{Type}}</b> · {{Mode}} · {{Importance}}</div>\n'
    '<div class="consigne">{{Consigne}}</div>\n'
    '{{#Contexte}}<div class="contexte"><i>Énoncé de référence :</i><br>{{Contexte}}</div>{{/Contexte}}'
)
_BACK = (
    "{{FrontSide}}\n<hr>\n"
    '<div class="attendu">{{Attendu}}</div>\n'
    '<div class="src">{{Titre}} — {{Chapitre}} / {{Lecon}} — {{SourceRef}}</div>'
)


class AnkiError(RuntimeError):
    pass


# Conservé pour compat : le reste du code attrape `anki.AnkiConnectError`.
AnkiConnectError = AnkiError

# --- Collection (singleton, accès sérialisé) --------------------------------
_LOCK = threading.RLock()
_COL = None
_COL_PATH = None


def configure(path: str) -> None:
    """Définit le chemin du fichier de collection (.anki2) à ouvrir."""
    global _COL_PATH
    _COL_PATH = path


def _col():
    global _COL
    if _COL is None:
        if not _COL_PATH:
            raise AnkiError("Collection non configurée (définis SAPIO_COLLECTION).")
        from anki.collection import Collection

        _COL = Collection(_COL_PATH)
    return _COL


def close() -> None:
    global _COL
    with _LOCK:
        if _COL is not None:
            _COL.close()
            _COL = None


# --- Lecture ----------------------------------------------------------------
def find_cards(query: str) -> list:
    with _LOCK:
        return list(_col().find_cards(query))


def find_notes(query: str) -> list:
    with _LOCK:
        return list(_col().find_notes(query))


def cards_info(card_ids: list) -> list:
    """Renvoie, par carte, {cardId, deckName, fields:{nom:{value,order}}}
    (même forme qu'AnkiConnect pour ne pas casser `fields_of`)."""
    with _LOCK:
        col = _col()
        out = []
        for cid in card_ids:
            c = col.get_card(cid)
            note = c.note()
            nt = note.note_type()
            fields = {f["name"]: {"value": note[f["name"]], "order": i} for i, f in enumerate(nt["flds"])}
            out.append({"cardId": cid, "deckName": col.decks.name(c.did), "fields": fields})
        return out


def fields_of(info: dict) -> dict:
    return {name: f["value"] for name, f in info.get("fields", {}).items()}


def deck_stats_map() -> dict:
    """{nom_complet_du_deck: {new, learn, review}} en respectant les limites du jour."""
    with _LOCK:
        tree = _col().sched.deck_due_tree()
        out: dict = {}

        def walk(node, prefix):
            full = (prefix + "::" + node.name) if prefix else node.name
            if node.name:
                out[full] = {"new": node.new_count, "learn": node.learn_count, "review": node.review_count}
                prefix = full
            for ch in node.children:
                walk(ch, prefix)

        walk(tree, "")
        return out


def deck_total_counts() -> dict:
    """{nom_complet: nombre total de cartes Sapio dans CE deck (hors sous-decks)}.

    Sert à consulter les decks (toutes les cartes, pas seulement celles dues).
    L'agrégation sur le sous-arbre est faite côté API.
    """
    with _LOCK:
        col = _col()
        out: dict = {}
        for cid in col.find_cards('note:"Sapio Restitution"'):
            name = col.decks.name(col.get_card(cid).did)
            out[name] = out.get(name, 0) + 1
        return out


def decks_of(card_ids: list) -> set:
    """Ensemble des noms de decks contenant les cartes données."""
    with _LOCK:
        col = _col()
        return {col.decks.name(col.get_card(c).did) for c in card_ids}


# --- Notation (scheduler v3) ------------------------------------------------
_RATING = None


def _rating_for(ease: int):
    global _RATING
    if _RATING is None:
        from anki import scheduler_pb2 as sp

        _RATING = {1: sp.CardAnswer.AGAIN, 2: sp.CardAnswer.HARD, 3: sp.CardAnswer.GOOD, 4: sp.CardAnswer.EASY}
    return _RATING[ease]


def answer_card(card_id: int, ease: int) -> bool:
    """Répond à une carte (ease 1..4) → FSRS replanifie."""
    with _LOCK:
        col = _col()
        card = col.get_card(card_id)
        card.start_timer()
        states = col._backend.get_scheduling_states(card_id)
        answer = col.sched.build_answer(card=card, states=states, rating=_rating_for(ease))
        col.sched.answer_card(answer)
        return True


def card_ids_of_notes(note_ids: list) -> list:
    """Cartes engendrées par une liste de notes (une carte par note ici)."""
    with _LOCK:
        col = _col()
        out: list = []
        for nid in note_ids:
            out.extend(col.get_note(nid).card_ids())
        return out


def seed_memory(card_ids: list, interval_days: int) -> int:
    """Préinitialise un niveau de maîtrise sur des cartes neuves.

    Les bascule en révision avec un intervalle ≈ `interval_days` (légère
    dispersion pour éviter un pic de révisions le même jour) et sème la mémoire
    FSRS : la stabilité est l'intervalle (à rétention 0.9, l'intervalle optimal
    ≈ la stabilité) et la difficulté est médiane. `factor` sert de filet si FSRS
    est désactivé (planification SM-2). Renvoie le nombre de cartes traitées.
    """
    if not card_ids or interval_days <= 0:
        return 0
    import random

    from anki.cards_pb2 import FsrsMemoryState

    with _LOCK:
        col = _col()
        today = col.sched.today
        n = 0
        for cid in card_ids:
            ivl = max(1, round(interval_days * random.uniform(0.85, 1.15)))
            card = col.get_card(cid)
            card.type = 2  # CARD_TYPE_REV
            card.queue = 2  # QUEUE_TYPE_REV
            card.reps = max(card.reps, 1)
            card.ivl = ivl
            card.due = today + ivl
            card.factor = 2500
            card.memory_state = FsrsMemoryState(stability=float(ivl), difficulty=5.0)
            col.update_card(card)
            n += 1
        return n


# --- Note type --------------------------------------------------------------
def ensure_model() -> None:
    with _LOCK:
        col = _col()
        m = col.models.by_name(MODEL_NAME)
        if m is None:
            m = col.models.new(MODEL_NAME)
            for f in FIELDS:
                col.models.add_field(m, col.models.new_field(f))
            t = col.models.new_template("Restitution")
            t["qfmt"] = _FRONT
            t["afmt"] = _BACK
            col.models.add_template(m, t)
            m["css"] = _CSS
            col.models.add(m)
            return
        existing = {f["name"] for f in m["flds"]}
        for f in FIELDS:
            if f not in existing:
                col.models.add_field(m, col.models.new_field(f))
        m["tmpls"][0]["qfmt"] = _FRONT
        m["tmpls"][0]["afmt"] = _BACK
        m["css"] = _CSS
        col.models.save(m)


# --- Écriture ---------------------------------------------------------------
def add_notes(notes: list) -> list:
    """Ajoute des notes (forme produite par card_to_note) ; renvoie les ids (ou None)."""
    with _LOCK:
        col = _col()
        res = []
        for n in notes:
            model = col.models.by_name(n["modelName"])
            note = col.new_note(model)
            for k, v in n["fields"].items():
                if k in note.keys():
                    note[k] = v
            note.tags = list(n.get("tags", []))
            did = col.decks.id(n["deckName"], create=True)
            try:
                col.add_note(note, did)
                res.append(note.id)
            except Exception:
                res.append(None)
        return res


def delete_notes(note_ids: list) -> int:
    with _LOCK:
        if not note_ids:
            return 0
        _col().remove_notes(note_ids)
        return len(note_ids)


def delete_decks(names: list) -> int:
    with _LOCK:
        col = _col()
        dids = [col.decks.id(n, create=False) for n in names]
        dids = [d for d in dids if d]
        if dids:
            col.decks.remove(dids)
        return len(dids)


def create_deck(name: str):
    with _LOCK:
        return _col().decks.id(name, create=True)


# --- Synchro AnkiWeb --------------------------------------------------------
def sync(direction: str | None = None) -> str:
    """Synchronise la collection avec AnkiWeb (identifiants via l'environnement).

    `direction` None → sync normal bidirectionnel. Si un *full sync* est requis
    (conflit), on NE tranche PAS automatiquement : on lève une erreur. Pour forcer,
    appeler avec direction="upload" (écrase AnkiWeb) ou "download" (écrase le local).
    Renvoie "ok" / "à jour" / "full-upload" / "full-download".
    """
    with _LOCK:
        col = _col()
        user = os.environ.get("ANKIWEB_USERNAME")
        pw = os.environ.get("ANKIWEB_PASSWORD")
        if not (user and pw):
            raise AnkiError("Identifiants AnkiWeb manquants (ANKIWEB_USERNAME / ANKIWEB_PASSWORD).")
        endpoint = os.environ.get("ANKIWEB_ENDPOINT") or None
        auth = col.sync_login(user, pw, endpoint)
        if direction in ("upload", "download"):
            # AnkiWeb redirige vers un serveur de sync précis (sync13, etc.).
            # Après login l'endpoint est vide : on le négocie via un sync normal
            # (qui se contente de constater qu'un full sync est requis), puis on
            # rejoue le full sur ce serveur, sinon AnkiWeb renvoie un 400.
            out = col.sync_collection(auth, sync_media=False)
            if out.new_endpoint:
                auth.endpoint = out.new_endpoint
            col.full_upload_or_download(auth=auth, server_usn=None, upload=(direction == "upload"))
            return "full-" + direction
        out = col.sync_collection(auth, sync_media=False)
        from anki import sync_pb2 as sp

        req = sp.SyncCollectionResponse.ChangesRequired
        if out.required in (req.NO_CHANGES, req.NORMAL_SYNC):
            return "à jour" if out.required == req.NO_CHANGES else "ok"
        name = sp.SyncCollectionResponse.ChangesRequired.Name(out.required)
        raise AnkiError(
            f"Synchro complète requise ({name}) — conflit. Résous-le dans Anki desktop, "
            "ou force avec une synchro upload/download explicite."
        )


# --- Construction d'une note (inchangé) -------------------------------------
def card_to_note(card: dict, deck_root: str, lookup: dict | None = None) -> dict:
    """Construit la note. `lookup` mappe (chapitre, leçon) → sous-chemin de deck ;
    à défaut, sous-deck = la leçon."""
    lookup = lookup or {}
    key = (card.get("chapitre", ""), card.get("lecon", ""))
    sub = lookup.get(key) or (card.get("lecon") or "Divers")
    return {
        "deckName": f"{deck_root}::{sub}",
        "modelName": MODEL_NAME,
        "fields": {
            "Consigne": latex_for_anki(card["consigne"]),
            "Attendu": latex_for_anki(card["attendu"]),
            "Type": TYPE_LABEL.get(card.get("type", ""), card.get("type", "")),
            "Mode": card["mode"],
            "Importance": card["importance"],
            "Titre": latex_for_anki(card["titre"]),
            "Chapitre": card.get("chapitre", ""),
            "Lecon": card.get("lecon", ""),
            "SourceRef": card.get("source_ref", ""),
            "Contexte": latex_for_anki(card.get("contexte", "")),
        },
        "tags": ["sapio", f"mode::{card['mode']}", f"importance::{card['importance']}"],
    }


def latex_for_anki(s: str) -> str:
    """Prépare le LaTeX pour un rendu HTML + MathJax (enumerate/emph → HTML,
    $$→\\[\\], $→\\(\\), listes en ligne et sauts de ligne → <br>)."""
    s = re.sub(r"\$\$(.+?)\$\$", r"\\[\1\\]", s, flags=re.S)
    s = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", r"\\(\1\\)", s, flags=re.S)
    s = re.sub(r"\\(?:emph|textit)\{(.*?)\}", r"<i>\1</i>", s, flags=re.S)
    s = re.sub(r"\\textbf\{(.*?)\}", r"<b>\1</b>", s, flags=re.S)
    s = s.replace(r"\begin{enumerate}", "<ol>").replace(r"\end{enumerate}", "</ol>")
    s = s.replace(r"\begin{itemize}", "<ul>").replace(r"\end{itemize}", "</ul>")
    s = re.sub(r"\\item\s*", "<li>", s)
    s = re.sub(r"([.;:])\s+(\d+\.\s)", r"\1<br>\2", s)
    s = s.replace("\n", "<br>")
    s = re.sub(r"<br>\s*(<li>|</?ol>|</?ul>)", r"\1", s)
    s = re.sub(r"(<ol>|<ul>)\s*<br>", r"\1", s)
    return s
