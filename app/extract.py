# SPDX-License-Identifier: AGPL-3.0-or-later
"""Étape (a) : lecture en vision d'un lot de pages → objets de cours structurés.

Deux providers possibles, choisis par `provider` :
- "anthropic"  : SDK anthropic, messages.parse (sortie structurée native).
- "openrouter" : API compatible OpenAI (SDK openai), sortie JSON parsée
  toléramment (les modèles gratuits ne garantissent pas le JSON schema strict).
"""

from __future__ import annotations

import base64
import json
import os

from .models import CourseObject, PageBatchExtraction

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Usage tokens accumulé sur le dernier run (lu par la CLI pour estimer le coût).
LAST_USAGE: list[dict] = []

SYSTEM = """\
Tu es un agrégatif de mathématiques qui dépouille un polycopié de cours pour en \
extraire la structure, en vue de préparer l'oral d'agrégation.

On te donne les images des pages d'un poly. Extrais-en les OBJETS DE COURS : \
définitions, théorèmes, propositions, lemmes, EXERCICES, et tout RÉSULTAT/CAS/FAIT \
important à connaître. Pour chacun :

- type : "definition", "theoreme", "proposition", "lemme" ou "exercice". Distingue :
    * "theoreme" : un résultat MAJEUR (le plus central) ;
    * "proposition" : un résultat important mais moins central qu'un théorème. \
      Utilise aussi "proposition" pour les RÉSULTATS / CAS / FAITS importants à \
      connaître même s'ils ne sont PAS encadrés comme tels (ex. : « si $X$ est \
      $\\mathscr G$-mesurable alors $\\mathbb E[X|\\mathscr G]=X$ », cas particuliers, \
      remarques-clés) ;
    * "lemme" : un résultat technique, étape intermédiaire ;
    * "exercice" : un exercice que l'élève doit savoir résoudre, OU un exemple / \
      contre-exemple présent dans le poly assez riche pour être justifié (voir RÈGLES).
  Respecte l'étiquette du poly quand elle existe (« Théorème », « Proposition »…).
- titre : le nom usuel (« Théorème de Baire », « Définition d'une martingale »…). \
À défaut, un titre court et descriptif.
- chapitre : le CHAPITRE du poly où il apparaît, avec son numéro si visible \
(ex. « 1. Définition dans le cas positif »).
- lecon : la PARTIE/SECTION précise au sein du chapitre, avec son numéro si visible \
(ex. « 1.2 Définition et unicité »). C'est le niveau le plus fin de découpage.
- source_ref : un repère dans le poly, le plus précis possible (ex. « §6.3 p.47 »). \
Utilise les numéros visibles sur la page.
- importance : juge la centralité pour une leçon d'agrég.
    * "central" : structurant, à maîtriser sous toutes ses facettes. Les théorèmes \
      majeurs et définitions fondamentales sont en général ici.
    * "standard" : résultat utile mais non central. Beaucoup de propositions.
    * "technique" : étape intermédiaire. Typiquement les lemmes.
- enonce : l'énoncé PRÉCIS, en LaTeX, avec TOUTES les hypothèses et quantificateurs. \
    Pour un exercice : l'énoncé complet de l'exercice.
- preuve : la démonstration complète en LaTeX si elle figure sur les pages, sinon "". \
    Si une preuve commence ou se poursuit hors des pages montrées, écris ce que tu \
    vois et ajoute « [preuve tronquée] ». Pour un EXERCICE : le corrigé — celui du \
    poly s'il existe, sinon rédige toi-même une solution rigoureuse et complète.
- idees_cles : les 2-3 idées MOTRICES de la preuve / de la résolution, sinon "".

RÈGLES :
- N'invente rien. N'extrais que ce qui est réellement sur les pages.
- EXEMPLES et CONTRE-EXEMPLES : ne les rattache pas à une définition. Quand le poly \
  présente un exemple ou un contre-exemple assez riche pour qu'il y ait quelque chose à \
  ÉTABLIR (montrer qu'un objet vérifie une notion, ou qu'il la met en défaut), émets-le \
  comme un objet de type "exercice" : `enonce` = la tâche reformulée en question \
  (« Montrer que ... est une tribu », « Montrer que ... n'est pas mesurable »), `preuve` \
  = la justification (celle du poly, sinon rédige-la). S'il est trivial ou purement \
  illustratif, ignore-le.
- Les champs non pertinents sont des chaînes vides "", jamais omis.
- Le contenu mathématique est en LaTeX.
- Ignore les pages de garde, tables des matières, et le texte de liaison sans contenu.
"""

# Décrit la forme JSON attendue (essentiel pour les providers sans schéma strict).
JSON_SHAPE = """\
FORMAT DE SORTIE : réponds UNIQUEMENT par un objet JSON valide, sans texte autour, \
de la forme :
{"objets": [{"type": "definition|theoreme|proposition|lemme|exercice", "titre": "...", \
"chapitre": "...", "lecon": "...", \
"source_ref": "...", "importance": "central|standard|technique", "enonce": "...", \
"preuve": "...", "idees_cles": "..."}]}
S'il n'y a aucun objet sur les pages, renvoie {"objets": []}.\
"""

USER_INSTRUCTION = "Extrais les objets de cours présents sur ces pages."


def _b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode("ascii")


def extract_objects(
    provider: str, model: str, pages: list[tuple[int, bytes]]
) -> list[CourseObject]:
    if provider == "anthropic":
        return _extract_anthropic(model, pages)
    if provider == "openrouter":
        return _extract_openrouter(model, pages)
    raise ValueError(f"provider inconnu : {provider!r} (anthropic | openrouter)")


def anthropic_parsed_stream(
    model, system, content, output_format, max_tokens=48000, effort="medium"
):
    """Appel Anthropic en STREAMING avec sortie structurée.

    Le streaming est requis dès qu'on vise > 16k tokens de sortie (garde non-stream
    du SDK) — indispensable pour traiter tout un chapitre en un seul appel. L'`effort`
    borne la réflexion (sinon elle peut épuiser le budget avant la fin du JSON).
    `content` est une chaîne ou une liste de blocs (texte/image).
    """
    import anthropic

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=output_format,
    ) as stream:
        msg = stream.get_final_message()
    u = getattr(msg, "usage", None)
    if u is not None:
        LAST_USAGE.append(
            {"model": model, "input": getattr(u, "input_tokens", 0) or 0,
             "output": getattr(u, "output_tokens", 0) or 0}
        )
    parsed = getattr(msg, "parsed_output", None)
    if parsed is None:
        raise RuntimeError(
            f"sortie structurée vide (stop_reason={getattr(msg, 'stop_reason', None)})"
        )
    return parsed


def _extract_anthropic(model: str, pages: list[tuple[int, bytes]]) -> list[CourseObject]:
    content: list[dict] = []
    for num, png in pages:
        content.append({"type": "text", "text": f"--- Page {num} ---"})
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": _b64(png)},
            }
        )
    content.append({"type": "text", "text": USER_INSTRUCTION})
    # Extraction : lecture + structuration → effort medium suffit, et large budget JSON.
    parsed = anthropic_parsed_stream(
        model, SYSTEM, content, PageBatchExtraction, max_tokens=48000, effort="medium"
    )
    return parsed.objets


def _extract_openrouter(model: str, pages: list[tuple[int, bytes]]) -> list[CourseObject]:
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY manquante (à mettre dans .env).")
    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

    content: list[dict] = []
    for num, png in pages:
        content.append({"type": "text", "text": f"--- Page {num} ---"})
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(png)}"}}
        )
    content.append({"type": "text", "text": USER_INSTRUCTION})

    messages = [
        {"role": "system", "content": SYSTEM + "\n\n" + JSON_SHAPE},
        {"role": "user", "content": content},
    ]
    kwargs = dict(model=model, messages=messages, max_tokens=16000)
    try:
        resp = client.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs
        )
    except Exception:
        # Certains modèles gratuits refusent response_format ; on réessaie sans.
        resp = client.chat.completions.create(**kwargs)

    u = getattr(resp, "usage", None)
    if u is not None:
        LAST_USAGE.append(
            {"model": model, "input": getattr(u, "prompt_tokens", 0) or 0,
             "output": getattr(u, "completion_tokens", 0) or 0}
        )
    text = resp.choices[0].message.content or ""
    data = _loads_tolerant(text)
    return [CourseObject.model_validate(_normalize(o)) for o in data.get("objets", [])]


# Les modèles ne respectent pas toujours l'enum : on normalise plutôt que de
# jeter l'objet (sinon on perd silencieusement de l'extraction).
_TYPE_ALIASES = {
    "théorème": "theoreme",
    "theoreme": "theoreme",
    "theorem": "theoreme",
    "proposition": "proposition",
    "corollaire": "proposition",
    "corollary": "proposition",
    "définition": "definition",
    "definition": "definition",
    "lemme": "lemme",
    "lemma": "lemme",
    "exercice": "exercice",
    "exercise": "exercice",
}
_VALID_TYPES = {"definition", "theoreme", "proposition", "lemme", "exercice"}
_VALID_IMPORTANCE = {"central", "standard", "technique"}
_STR_FIELDS = (
    "titre",
    "chapitre",
    "lecon",
    "source_ref",
    "enonce",
    "preuve",
    "idees_cles",
)


def _normalize(o: dict) -> dict:
    o = dict(o)
    t = str(o.get("type", "")).strip().lower()
    o["type"] = _TYPE_ALIASES.get(t, t if t in _VALID_TYPES else "theoreme")
    imp = str(o.get("importance", "")).strip().lower()
    o["importance"] = imp if imp in _VALID_IMPORTANCE else "standard"
    for f in _STR_FIELDS:
        v = o.get(f)
        o[f] = "" if v is None else str(v)
    return o


def suggest_taxonomy(provider: str, model: str, objects):
    """Suggère {annee, cours} à partir des chapitres/intitulés extraits (appel court)."""
    from .models import Suggestion

    chap = "; ".join(sorted({o.chapitre for o in objects if o.chapitre}))
    titres = "; ".join(o.titre for o in objects[:25])
    system = (
        "Tu classes un cours de mathématiques. À partir des chapitres et intitulés, "
        "propose : annee = le niveau d'études probable (ex. « MPSI », « L3 », "
        "« Master 1 », « Prépa agrég ») ; cours = le nom court de la matière (ex. "
        "« Probabilités », « Espaces vectoriels normés »). Reste concis."
    )
    user = f"Chapitres : {chap}\nObjets : {titres}"
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        r = client.messages.parse(
            model=model, max_tokens=400, system=system,
            messages=[{"role": "user", "content": user}], output_format=Suggestion,
        )
        return r.parsed_output
    if provider == "openrouter":
        from openai import OpenAI

        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])
        msgs = [
            {"role": "system", "content": system + ' Réponds en JSON {"annee":"...","cours":"..."}'},
            {"role": "user", "content": user},
        ]
        try:
            resp = client.chat.completions.create(model=model, messages=msgs, max_tokens=200, response_format={"type": "json_object"})
        except Exception:
            resp = client.chat.completions.create(model=model, messages=msgs, max_tokens=200)
        d = _loads_tolerant(resp.choices[0].message.content or "{}")
        return Suggestion(annee=str(d.get("annee", "")), cours=str(d.get("cours", "")))
    raise ValueError(f"provider inconnu : {provider!r}")


def _loads_tolerant(text: str) -> dict:
    """Parse un objet JSON même si le modèle l'entoure de texte ou de ```json."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Réponse non-JSON du modèle : {text[:200]!r}")
