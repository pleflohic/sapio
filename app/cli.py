# SPDX-License-Identifier: AGPL-3.0-or-later
"""CLI du prototype de génération.

    sapio extract <poly.pdf> [options]

Pipeline : pages PDF → vision (objets de cours) → expansion graduée (cartes).
Produit deux fichiers JSON : les objets (relisibles/ajustables) et les cartes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import anki_backend as anki, bilan, history, pdf, review, settings
from .cards import expand_all
from .extract import extract_objects
from .models import CourseObject

# Défauts codés, surchargeables par l'environnement (.env), eux-mêmes
# surchargeables par les flags CLI. Précédence : flag CLI > .env > défaut codé.
DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODELS = {
    "openrouter": "google/gemma-4-31b-it:free",
    "anthropic": "claude-opus-4-8",
}
DEFAULT_DPI = 150
DEFAULT_BATCH_PAGES = 0  # 0 = toute la plage en un seul appel (contexte complet)


def _load_dotenv() -> None:
    """Charge un .env minimal (KEY=value) depuis le dossier courant ou le projet.

    Sans dépendance externe ; n'écrase pas une variable déjà définie.
    """
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


def _parse_pages(spec: str | None, total: int) -> tuple[int, int]:
    """Interprète --pages : "all", "5", "3-12". Borne sur [1, total]."""
    if spec is None or spec == "all":
        return 1, total
    if "-" in spec:
        a, b = spec.split("-", 1)
        first, last = int(a), int(b)
    else:
        first = last = int(spec)
    return max(1, first), min(total, last)


def cmd_extract(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(f"Fichier introuvable : {pdf_path}", file=sys.stderr)
        return 1

    provider = args.provider
    model = args.model or DEFAULT_MODELS.get(provider)
    if not model:
        print(f"Aucun modèle par défaut pour le provider {provider!r}.", file=sys.stderr)
        return 1

    total = pdf.page_count(pdf_path)
    first, last = _parse_pages(args.pages, total)
    print(f"PDF : {pdf_path.name} ({total} pages). Pages {first}–{last}.")
    print(f"Provider : {provider} — modèle : {model}")

    objects: list[CourseObject] = []
    step = args.batch_pages if args.batch_pages and args.batch_pages > 0 else (last - first + 1)
    page = first
    while page <= last:
        batch_last = min(page + step - 1, last)
        pages = pdf.render_pages(pdf_path, page, batch_last, dpi=args.dpi)
        print(f"  → lecture des pages {page}–{batch_last}…", flush=True)
        try:
            found = extract_objects(provider, model, pages)
        except Exception as e:
            print(f"\nÉchec de l'appel modèle : {type(e).__name__}: {e}", file=sys.stderr)
            print(
                "Vérifie ta clé (OPENROUTER_API_KEY / ANTHROPIC_API_KEY) dans .env "
                "et le provider/modèle choisis.",
                file=sys.stderr,
            )
            return 1
        objects.extend(found)
        print(f"    {len(found)} objet(s) extrait(s).")
        page = batch_last + 1

    objects_out = Path(args.objects_out)
    objects_out.write_text(
        json.dumps([o.model_dump() for o in objects], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cards = expand_all(objects)
    cards_out = Path(args.out)
    cards_out.write_text(
        json.dumps([c.model_dump() for c in cards], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    from .cards import default_deck_map

    decks_out = Path(args.decks_out)
    decks_out.write_text(
        json.dumps(default_deck_map(cards), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _summary(objects, cards)
    _usage_summary()
    print(f"\nObjets  → {objects_out}")
    print(f"Cartes  → {cards_out}")
    print(f"Decks   → {decks_out}  (édite le champ « deck » pour choisir tes sous-decks)")
    return 0


# Prix indicatifs $/M tokens (entrée, sortie). La sortie inclut la réflexion.
_PRICE = {
    "claude-opus-4-8": (5, 25),
    "claude-opus-4-7": (5, 25),
    "claude-sonnet-4-6": (3, 15),
    "claude-haiku-4-5": (1, 5),
}


def _usage_summary() -> None:
    from .extract import LAST_USAGE

    if not LAST_USAGE:
        return
    tin = sum(u["input"] for u in LAST_USAGE)
    tout = sum(u["output"] for u in LAST_USAGE)
    cost = 0.0
    for u in LAST_USAGE:
        pin, pout = _PRICE.get(u["model"], (0, 0))
        cost += u["input"] / 1e6 * pin + u["output"] / 1e6 * pout
    line = f"  Tokens : entrée {tin:,} · sortie {tout:,} (réflexion incluse)"
    if cost:
        line += f"  →  ~${cost:.3f}"
    print(line)


def _summary(objects: list[CourseObject], cards) -> None:
    from collections import Counter

    by_imp = Counter(o.importance.value for o in objects)
    by_mode = Counter(c.mode for c in cards)
    print(f"\n{len(objects)} objets → {len(cards)} cartes")
    print("  Importance :", dict(by_imp))
    print("  Modes      :", dict(by_mode))


def cmd_push(args: argparse.Namespace) -> int:
    cards_path = Path(args.cards)
    if not cards_path.is_file():
        print(f"Fichier de cartes introuvable : {cards_path}", file=sys.stderr)
        return 1
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    if not cards:
        print("Aucune carte à envoyer.")
        return 0

    from .cards import deck_lookup

    lookup = {}
    decks_path = Path(args.decks)
    if decks_path.is_file():
        lookup = deck_lookup(json.loads(decks_path.read_text(encoding="utf-8")))
    notes = [anki.card_to_note(c, args.deck, lookup) for c in cards]
    decks = sorted({n["deckName"] for n in notes})

    if args.dry_run:
        print(f"[dry-run] {len(notes)} notes, note type « {anki.MODEL_NAME} »")
        print("[dry-run] decks :", ", ".join(decks))
        print("[dry-run] exemple de note :")
        print(json.dumps(notes[0], ensure_ascii=False, indent=2))
        return 0

    try:
        anki.ensure_model()
        result = anki.add_notes(notes)  # crée les decks au passage
    except anki.AnkiError as e:
        print(f"\nÉchec Anki : {e}", file=sys.stderr)
        return 1

    added = sum(1 for r in result if r is not None)
    skipped = len(result) - added
    print(f"{added} note(s) ajoutée(s)" + (f", {skipped} ignorée(s) (doublons)" if skipped else ""))
    print(f"Deck(s) : {', '.join(decks)}")
    return 0


def _read_image(prompt: str) -> bytes | str | None:
    """Lit un chemin de photo au clavier. Renvoie les octets, ou 'skip'/'quit'."""
    while True:
        raw = input(prompt).strip()
        if raw in ("skip", "quit", ""):
            return raw or "skip"
        p = Path(raw).expanduser()
        if p.is_file():
            return p.read_bytes()
        print(f"  introuvable : {p} (ou tape 'skip' / 'quit')")


def cmd_review(args: argparse.Namespace) -> int:
    provider = args.provider
    model = args.model or DEFAULT_MODELS.get(provider)

    try:
        ids = anki.find_cards(args.query)
    except anki.AnkiError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    if not ids:
        print(f"Aucune carte à réviser pour : {args.query}")
        return 0
    ids = ids[: args.limit]
    infos = {i["cardId"]: i for i in anki.cards_info(ids)}
    print(f"{len(ids)} carte(s) à réviser. Provider : {provider} — {model}.")
    print("Pour chaque carte : rédige sur papier, puis donne le chemin de ta photo "
          "(ou 'skip' / 'quit').\n")

    reviewed = 0
    for cid in ids:
        info = infos.get(cid)
        if not info:
            continue
        f = anki.fields_of(info)
        card = {
            "mode": f.get("Mode", ""), "consigne": f.get("Consigne", ""),
            "attendu": f.get("Attendu", ""), "titre": f.get("Titre", ""),
            "lecon": f.get("Lecon", ""), "importance": f.get("Importance", ""),
        }
        print("─" * 70)
        print(f"[{card['mode']} · {card['importance']}] {card['titre']}")
        print(f"CONSIGNE : {card['consigne']}\n")

        img = _read_image("  photo › ")
        if img == "quit":
            break
        if img == "skip":
            print("  (sautée)\n")
            continue

        try:
            ev = review.evaluate(provider, model, card, img)
            # Boucle de confirmation des doutes (règle ferme, spec §6).
            if ev.doutes:
                print(f"\n  ⚠️  Confiance de lecture : {ev.confiance}. Quelques doutes :")
                clarifs = []
                for d in ev.doutes:
                    ans = input(f"    • {d.question}\n      › ").strip()
                    clarifs.append(f"{d.passage} → {ans}")
                ev = review.evaluate(provider, model, card, img, clarifications=clarifs)
        except Exception as e:
            print(f"  Échec de l'évaluation : {type(e).__name__}: {e}", file=sys.stderr)
            print("  (vérifie la clé du provider)\n")
            continue

        ease = review.RATING_TO_EASE[ev.note]
        print(f"\n  FEEDBACK : {ev.feedback}")
        print(f"\n  → Note : {ev.note.upper()} (ease {ease}) — {ev.justification}")
        try:
            anki.answer_card(cid, ease)
        except anki.AnkiError as e:
            print(f"  (réponse à la carte échouée : {e})", file=sys.stderr)
        history.append(
            args.history,
            {
                "card_id": cid, "lecon": card["lecon"], "titre": card["titre"],
                "mode": card["mode"], "importance": card["importance"],
                "note": ev.note, "ease": ease, "feedback": ev.feedback,
            },
        )
        reviewed += 1
        print()

    print("─" * 70)
    print(f"Session terminée : {reviewed} carte(s) révisée(s). Historique → {args.history}")
    # Bilan cumulatif automatique en fin de session (spec §8).
    try:
        out = bilan.build(history.load(args.history), args.bilan_out)
        print(f"Bilan PDF cumulatif → {out}")
    except Exception as e:
        print(f"(bilan non généré : {e})")
    return 0


def cmd_bilan(args: argparse.Namespace) -> int:
    records = history.load(args.history)
    if not records:
        print(f"Historique vide ({args.history}).")
        return 0
    try:
        out = bilan.build(records, args.out)
    except Exception as e:
        print(f"Échec : {e}", file=sys.stderr)
        return 1
    print(f"Bilan PDF → {out} ({len(records)} restitutions)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from . import api  # import tardif : Flask n'est requis que pour `serve`

    # provider / modèles / collection / dpi viennent désormais des préférences
    # (settings.json, éditables depuis l'onglet Paramètres). Ici on ne passe que
    # les réglages opérationnels propres à cette commande.
    config = {
        "query": args.query, "limit": args.limit,
        "history": args.history, "bilan_out": args.bilan_out,
    }
    app = api.create_api(config)
    s = settings.get()
    print(f"Sapio web → http://{args.host}:{args.port}  "
          f"(provider {s['provider']} — extraction {s['extract_model']} / notation {s['review_model']})")
    print(f"Depuis ton téléphone (même réseau) : http://<IP-de-cet-ordi>:{args.port}")
    app.run(host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Défauts résolus depuis l'environnement (chargé par _load_dotenv avant ici).
    provider = os.environ.get("SAPIO_PROVIDER", DEFAULT_PROVIDER)
    # Modèle par étape : un modèle économique pour l'extraction, un modèle
    # de pointe pour la notation. Repli : SAPIO_MODEL puis défaut du provider.
    extract_model = os.environ.get("SAPIO_EXTRACT_MODEL") or os.environ.get("SAPIO_MODEL")
    review_model = os.environ.get("SAPIO_REVIEW_MODEL") or os.environ.get("SAPIO_MODEL")
    dpi = int(os.environ.get("SAPIO_DPI", DEFAULT_DPI))
    batch = int(os.environ.get("SAPIO_BATCH_PAGES", DEFAULT_BATCH_PAGES))

    p = argparse.ArgumentParser(prog="sapio", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("extract", help="Génère des cartes à partir d'un poly PDF.")
    e.add_argument("pdf", help="Chemin du poly PDF.")
    e.add_argument(
        "--provider",
        default=provider,
        choices=["openrouter", "anthropic"],
        help=f"Fournisseur du modèle (défaut {provider}).",
    )
    e.add_argument(
        "--model",
        default=extract_model,
        help="Modèle d'extraction (défaut : SAPIO_EXTRACT_MODEL).",
    )
    e.add_argument("--pages", default="all", help='Pages : "all", "5" ou "3-12".')
    e.add_argument(
        "--batch-pages", type=int, default=batch,
        help="Pages par appel vision ; 0 = toute la plage en un seul appel (défaut, "
        "recommandé pour garder le contexte). >0 : découpe (utile pour de très gros polys).",
    )
    e.add_argument("--dpi", type=int, default=dpi, help=f"Résolution de rendu (défaut {dpi}).")
    e.add_argument("--out", default="cards.json", help="Sortie cartes (défaut cards.json).")
    e.add_argument(
        "--objects-out",
        default="objects.json",
        help="Sortie objets intermédiaires (défaut objects.json).",
    )
    e.add_argument(
        "--decks-out",
        default="decks.json",
        help="Sortie du mapping de decks éditable (défaut decks.json).",
    )
    e.set_defaults(func=cmd_extract)

    pu = sub.add_parser("push", help="Envoie cards.json vers Anki via AnkiConnect.")
    pu.add_argument("--cards", default="cards.json", help="Fichier de cartes (défaut cards.json).")
    pu.add_argument(
        "--decks", default="decks.json",
        help="Mapping de decks édité (défaut decks.json ; ignoré s'il manque).",
    )
    pu.add_argument("--deck", default="Sapio", help="Deck racine (défaut Sapio).")
    pu.add_argument(
        "--url", default="http://localhost:8765", help="URL AnkiConnect (défaut localhost:8765)."
    )
    pu.add_argument(
        "--dry-run", action="store_true", help="N'envoie rien ; montre ce qui serait créé."
    )
    pu.add_argument(
        "--allow-duplicates", action="store_true", help="Autorise les doublons à l'ajout."
    )
    pu.set_defaults(func=cmd_push)

    r = sub.add_parser("review", help="Session de révision (photo → feedback → bouton).")
    r.add_argument(
        "--provider", default=provider, choices=["openrouter", "anthropic"],
        help=f"Fournisseur (défaut {provider}).",
    )
    r.add_argument("--model", default=review_model, help="Modèle de notation (défaut : SAPIO_REVIEW_MODEL).")
    r.add_argument(
        "--query", default="deck:Sapio* is:due",
        help="Requête Anki des cartes à réviser (défaut 'deck:Sapio* is:due').",
    )
    r.add_argument("--limit", type=int, default=20, help="Nb max de cartes (défaut 20).")
    r.add_argument("--url", default="http://localhost:8765", help="URL AnkiConnect.")
    r.add_argument("--history", default="history.json", help="Fichier d'historique.")
    r.add_argument("--bilan-out", default="bilan.pdf", help="PDF de bilan en fin de session.")
    r.set_defaults(func=cmd_review)

    b = sub.add_parser("bilan", help="Génère le bilan PDF cumulatif depuis l'historique.")
    b.add_argument("--history", default="history.json", help="Fichier d'historique.")
    b.add_argument("--out", default="bilan.pdf", help="PDF de sortie (défaut bilan.pdf).")
    b.set_defaults(func=cmd_bilan)

    s = sub.add_parser("serve", help="Lance l'application web de révision.")
    s.add_argument(
        "--provider", default=provider, choices=["openrouter", "anthropic"],
        help=f"Fournisseur (défaut {provider}).",
    )
    s.add_argument("--model", default=review_model, help="Modèle de notation (défaut : SAPIO_REVIEW_MODEL).")
    s.add_argument("--host", default="0.0.0.0", help="Hôte d'écoute (défaut 0.0.0.0).")
    s.add_argument("--port", type=int, default=5000, help="Port (défaut 5000).")
    s.add_argument("--query", default="deck:Sapio* is:due", help="Requête Anki des cartes.")
    s.add_argument("--limit", type=int, default=20, help="Nb max de cartes (défaut 20).")
    s.add_argument("--url", default="http://localhost:8765", help="URL AnkiConnect.")
    s.add_argument("--history", default="history.json", help="Fichier d'historique.")
    s.add_argument("--bilan-out", default="bilan.pdf", help="PDF de bilan.")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()  # amorce l'environnement (secrets + défauts) depuis .env
    settings.load()  # préférences : settings.json (sinon défauts issus de l'env)
    settings.apply()  # configure la collection
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
