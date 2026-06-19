# SPDX-License-Identifier: AGPL-3.0-or-later
"""Boucle de révision — lecture et notation d'une copie manuscrite.

Cœur « runtime » de Sapio (spec_sapio.md §6). Deux usages :

- CLI `review` (une carte / une photo) : `evaluate()` lit + note en un coup.
- App web (session du jour, une seule capture) : flux en 3 temps —
  `transcribe_batch()` (vision : ce que le modèle lit, en LaTeX, à faire valider)
  puis, après confirmation/édition par l'élève, `grade_batch()` (texte seul :
  note la transcription validée contre l'attendu). On ne note jamais sur une
  lecture non confirmée.

Provider : même mécanisme que l'extraction (anthropic | openrouter).
"""

from __future__ import annotations

import base64
import json
import os

from .models import BatchGrade, BatchTranscription, Evaluation

# Note → ease AnkiConnect (answerCards attend 1..4).
RATING_TO_EASE = {"again": 1, "hard": 2, "good": 3, "easy": 4}

# Grille d'évaluation par mode (spec §4 / §7).
_RUBRIQUES = {
    "enoncer": "Fidélité EXACTE à l'énoncé attendu : toutes les hypothèses, tous les "
    "quantificateurs, rien en trop. Une hypothèse oubliée ou un quantificateur faux est grave.",
    "preuve": "L'élève doit dégager l'idée directrice PUIS rédiger la preuve avec une rigueur "
    "COMPLÈTE : chaque étape justifiée, toutes les hypothèses utilisées, aucun cercle logique, "
    "aucune étape bâclée. Une étape clé manquante ou fausse → Again.",
    "exemple": "L'objet proposé satisfait-il réellement la propriété demandée, et est-il bien "
    "justifié ? Plusieurs réponses correctes sont possibles : juge la validité, pas la conformité.",
    "contre_exemple": "L'objet proposé est-il un contre-exemple VALIDE (il met bien en défaut la "
    "propriété) et correctement justifié ?",
    "plan": "Le plan reconstruit est-il complet (toutes les grandes parties), bien ordonné, "
    "équilibré, avec les notions à la bonne place ?",
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _rubrique(mode: str) -> str:
    return _RUBRIQUES.get(mode, "Évalue la pertinence et la correction de la réponse.")


# ----------------------------------------------------------------------------
# CLI : évaluation directe d'une carte (lecture + note en un coup).
# ----------------------------------------------------------------------------

SYSTEM = """\
Tu es un examinateur d'agrégation de mathématiques, exigeant mais bienveillant. \
On te donne une CONSIGNE, le MODE d'évaluation, la RÉPONSE ATTENDUE (référence figée \
issue du cours), et une PHOTO de la copie manuscrite de l'élève.

Lis la copie, compare-la à l'attendu selon la grille du mode, rends un feedback ciblé, \
et choisis le bouton : again (faux / hypothèse ou étape clé manquante) · hard (correct \
mais lacunaire) · good (complet et rigoureux) · easy (impeccable).

RÈGLE FERME : si un passage décisif est illisible/ambigu, ne tranche pas à l'aveugle — \
mets-le dans "doutes" (question précise) et donne une note provisoire prudente. Indique \
ta "confiance" de lecture : haute / moyenne / faible.\
"""

JSON_SHAPE = """\
FORMAT DE SORTIE : réponds UNIQUEMENT par un objet JSON valide :
{"lecture": "...", "confiance": "haute|moyenne|faible", \
"doutes": [{"passage": "...", "question": "..."}], "feedback": "...", \
"note": "again|hard|good|easy", "justification": "..."}\
"""


def _prompt_text(card: dict, clarifications: list[str] | None) -> str:
    parts = [
        f"MODE : {card['mode']}",
        f"GRILLE : {_rubrique(card['mode'])}",
        f"CONSIGNE : {card['consigne']}",
        f"RÉPONSE ATTENDUE (référence) :\n{card['attendu']}",
        "Voici la photo de la copie manuscrite de l'élève :",
    ]
    if clarifications:
        parts.append(
            "L'élève a répondu à tes doutes de lecture :\n- " + "\n- ".join(clarifications)
            + "\nTiens-en compte et finalise sans nouveau doute sur ces points."
        )
    return "\n\n".join(parts)


def evaluate(provider, model, card, image, clarifications=None) -> Evaluation:
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        content = [
            {"type": "text", "text": _prompt_text(card, clarifications)},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(image)}},
        ]
        resp = client.messages.parse(
            model=model, max_tokens=8000, thinking={"type": "adaptive"},
            system=SYSTEM, messages=[{"role": "user", "content": content}],
            output_format=Evaluation,
        )
        return resp.parsed_output
    if provider == "openrouter":
        from openai import OpenAI

        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])
        content = [
            {"type": "text", "text": _prompt_text(card, clarifications)},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(image)}"}},
        ]
        messages = [{"role": "system", "content": SYSTEM + "\n\n" + JSON_SHAPE},
                    {"role": "user", "content": content}]
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, max_tokens=4000,
                response_format={"type": "json_object"})
        except Exception:
            resp = client.chat.completions.create(model=model, messages=messages, max_tokens=4000)
        return _parse_one(resp.choices[0].message.content or "", Evaluation, single=True)
    raise ValueError(f"provider inconnu : {provider!r}")


# ----------------------------------------------------------------------------
# Web : 1) transcription (vision) → 2) notation (texte seul).
# ----------------------------------------------------------------------------

SYSTEM_TRANSCRIBE = """\
On te donne la liste des cartes du jour (numéro, consigne) et une ou plusieurs PHOTOS \
d'une copie manuscrite, où l'élève a NUMÉROTÉ ses réponses (1, 2, 3, …).

Ta seule tâche ici est de LIRE, pas de juger. Pour CHAQUE carte :
- retrouve la réponse correspondante (par le numéro ET le contenu) ;
- si l'élève ne l'a pas traitée, mets "traitee": false ;
- sinon, transcris fidèlement ce qu'il a écrit, en LaTeX, dans "lecture" (n'ajoute, ne \
corrige, n'embellis rien : c'est une transcription, pas une correction) ;
- indique ta "confiance" de lecture (haute/moyenne/faible) et mets les passages \
illisibles/ambigus dans "doutes" (avec une question précise).

Ne donne AUCUNE note ni feedback à ce stade.\
"""

JSON_SHAPE_TRANSCRIBE = """\
FORMAT DE SORTIE : objet JSON valide uniquement :
{"transcriptions": [{"numero": 1, "traitee": true, "lecture": "<latex>", \
"confiance": "haute|moyenne|faible", "doutes": [{"passage": "...", "question": "..."}]}]}
Une entrée par carte, dans l'ordre des numéros.\
"""

SYSTEM_GRADE = """\
Tu es un examinateur d'agrégation de mathématiques, exigeant mais bienveillant. Pour \
chaque carte on te donne : le mode et sa grille, la consigne, la réponse attendue, et la \
TRANSCRIPTION (en LaTeX, validée par l'élève) de ce qu'il a écrit. Il n'y a PAS d'image : \
tu juges le texte transcrit, considéré comme fidèle.

Pour chaque carte, évalue selon la grille du mode, rédige un feedback ciblé (hypothèse \
oubliée, étape bâclée, cercle logique, exemple mal choisi…) et choisis la note : \
again (faux / étape ou hypothèse clé manquante) · hard (correct mais lacunaire) · \
good (complet et rigoureux) · easy (impeccable).\
"""

JSON_SHAPE_GRADE = """\
FORMAT DE SORTIE : objet JSON valide uniquement :
{"grades": [{"numero": 1, "feedback": "...", "note": "again|hard|good|easy", \
"justification": "..."}]}\
"""


def transcribe_batch(provider, model, cards, images) -> BatchTranscription:
    """Lit la copie et renvoie, par carte, la transcription LaTeX à faire valider."""
    blocs = "\n".join(f"- Carte {c['numero']} : {c['consigne']}" for c in cards)
    prompt = f"Cartes du jour :\n{blocs}\n\nLes photos suivent."
    if provider == "anthropic":
        from .extract import anthropic_parsed_stream

        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(img)}})
        # Transcription = lecture pure → effort faible.
        return anthropic_parsed_stream(
            model, SYSTEM_TRANSCRIBE, content, BatchTranscription, max_tokens=32000, effort="low"
        )
    if provider == "openrouter":
        from openai import OpenAI

        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(img)}"}})
        messages = [{"role": "system", "content": SYSTEM_TRANSCRIBE + "\n\n" + JSON_SHAPE_TRANSCRIBE},
                    {"role": "user", "content": content}]
        try:
            resp = client.chat.completions.create(model=model, messages=messages, max_tokens=12000, response_format={"type": "json_object"})
        except Exception:
            resp = client.chat.completions.create(model=model, messages=messages, max_tokens=12000)
        return _parse_transcribe(resp.choices[0].message.content or "")
    raise ValueError(f"provider inconnu : {provider!r}")


def grade_batch(provider, model, cards) -> BatchGrade:
    """Note les transcriptions validées (texte seul). `cards` porte 'lecture'."""
    blocs = []
    for c in cards:
        blocs.append(
            f"### Carte {c['numero']} — mode {c['mode']}\n"
            f"GRILLE : {_rubrique(c['mode'])}\n"
            f"CONSIGNE : {c['consigne']}\n"
            f"RÉPONSE ATTENDUE :\n{c['attendu']}\n"
            f"TRANSCRIPTION DE L'ÉLÈVE (validée) :\n{c['lecture']}"
        )
    prompt = "Évalue chaque carte :\n\n" + "\n\n".join(blocs)
    if provider == "anthropic":
        from .extract import anthropic_parsed_stream

        # Notation = jugement de rigueur → effort élevé.
        return anthropic_parsed_stream(
            model, SYSTEM_GRADE, prompt, BatchGrade, max_tokens=32000, effort="high"
        )
    if provider == "openrouter":
        from openai import OpenAI

        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])
        messages = [{"role": "system", "content": SYSTEM_GRADE + "\n\n" + JSON_SHAPE_GRADE},
                    {"role": "user", "content": prompt}]
        try:
            resp = client.chat.completions.create(model=model, messages=messages, max_tokens=12000, response_format={"type": "json_object"})
        except Exception:
            resp = client.chat.completions.create(model=model, messages=messages, max_tokens=12000)
        return _parse_grade(resp.choices[0].message.content or "")
    raise ValueError(f"provider inconnu : {provider!r}")


# ----------------------------------------------------------------------------
# Parsing tolérant (providers sans schéma strict).
# ----------------------------------------------------------------------------

def _loads(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s : e + 1])


def _parse_one(text: str, _model, single=True) -> Evaluation:
    data = _loads(text)
    note = str(data.get("note", "")).strip().lower()
    data["note"] = note if note in RATING_TO_EASE else "again"
    data.setdefault("doutes", [])
    for f in ("lecture", "confiance", "feedback", "justification"):
        data.setdefault(f, "")
    return Evaluation.model_validate(data)


def _parse_transcribe(text: str) -> BatchTranscription:
    data = _loads(text)
    for t in data.get("transcriptions", []):
        t.setdefault("traitee", True)
        t.setdefault("doutes", [])
        for f in ("lecture", "confiance"):
            t.setdefault(f, "")
    return BatchTranscription.model_validate(data)


def _parse_grade(text: str) -> BatchGrade:
    data = _loads(text)
    for g in data.get("grades", []):
        note = str(g.get("note", "")).strip().lower()
        g["note"] = note if note in RATING_TO_EASE else "again"
        for f in ("feedback", "justification"):
            g.setdefault(f, "")
    return BatchGrade.model_validate(data)
