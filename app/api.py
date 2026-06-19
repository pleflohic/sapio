# SPDX-License-Identifier: AGPL-3.0-or-later
"""API JSON pour la SPA React (option A).

Réutilise toute la logique métier (AnkiConnect, transcription/notation Claude,
historique, bilan). Le front React consomme ces endpoints ; Flask sert aussi le
build statique de la SPA (même origine → pas de CORS). État de session
mono-utilisateur dans un global, comme l'app web historique.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections import Counter
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from . import anki_backend as anki, bilan, cards as cards_mod, extract, history, pdf, review, settings

# Phases de révision (du superficiel au profond) — `enoncer` d'abord pour éviter
# la fuite de contexte. Réutilisé du module web pour rester l'unique source.
from .web import PHASES, _MODE_RANK  # noqa: E402

STATE: dict = {}

# Jobs de génération en arrière-plan. La génération d'un poly entier dépasse
# largement le timeout d'un reverse-proxy (Cloudflare coupe vers 100 s), donc on
# ne tient pas une longue requête : on lance un thread et le front interroge
# l'avancement. Registre mono-process (un seul worker gunicorn).
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()

_TYPE_COLOR = {
    "Définition": "def",
    "Proposition": "prop",
    "Lemme": "prop",
    "Théorème": "theo",
    "Exercice": "exo",
}

DIST = Path(__file__).resolve().parent / "frontend" / "dist"

# Taille de lot par défaut pour la génération web (pages par appel au LLM).
# Surchargeable par SAPIO_BATCH_PAGES. Évite de dépasser le budget de sortie.
_GEN_BATCH_PAGES = 10

# Niveau de maîtrise initial par sous-deck → intervalle FSRS (jours). « neuf »
# laisse la carte en état neuf (comportement par défaut, aucun amorçage).
_MASTERY_DAYS = {"neuf": 0, "vu": 3, "correct": 10, "solide": 30, "acquis": 90}


def _parse_pages(spec: str, total: int) -> tuple[int, int]:
    if not spec or spec == "all":
        return 1, total
    if "-" in spec:
        a, b = spec.split("-", 1)
        return max(1, int(a)), min(total, int(b))
    n = int(spec)
    return max(1, n), min(total, n)


def _sapio_leaf_decks() -> set:
    """Decks (feuilles) contenant des cartes Sapio, identifiées par le note type."""
    ids = anki.find_cards('note:"Sapio Restitution"')
    return anki.decks_of(ids) if ids else set()


def _all_deck_names(leaves: set) -> list:
    names = set()
    for d in leaves:
        parts = d.split("::")
        for i in range(len(parts)):
            names.add("::".join(parts[: i + 1]))
    return sorted(names)


def _taxonomy(leaves: set) -> dict:
    """{annees: [...], cours: {annee: [cours...]}} d'après les 2 premiers niveaux."""
    annees: dict = {}
    for d in leaves:
        parts = d.split("::")
        annees.setdefault(parts[0], set())
        if len(parts) >= 2:
            annees[parts[0]].add(parts[1])
    return {"annees": sorted(annees), "cours": {a: sorted(c) for a, c in annees.items()}}


def _public_card(c: dict) -> dict:
    """Champs exposés au front (on NE renvoie PAS `attendu` : référence côté serveur)."""
    return {
        "numero": c["numero"], "card_id": c["card_id"], "type": c.get("type", ""),
        "color": _TYPE_COLOR.get(c.get("type", ""), ""), "mode": c.get("mode", ""),
        "importance": c.get("importance", ""), "consigne": c.get("consigne", ""),
        "contexte": c.get("contexte", ""), "titre": c.get("titre", ""),
        "lecon": c.get("lecon", ""),
    }


def _gen_cache_path() -> Path:
    """Fichier où l'on persiste la dernière génération, pour que l'import survive
    à un redémarrage du serveur (l'état mémoire, lui, est volatil)."""
    return settings._config_dir() / "last_gen.json"


def _save_gen(gen: dict) -> None:
    try:
        p = _gen_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(gen), encoding="utf-8")
    except OSError:
        pass


def _load_gen() -> dict | None:
    try:
        return json.loads(_gen_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _run_generation(job_id: str, tmp_path: str, spec: str, s: dict, batch: int, dpi: int) -> None:
    """Lit le poly lot par lot en arrière-plan et publie le résultat dans _JOBS.

    Un lot en échec est signalé sans faire planter le reste. `done` est incrémenté
    à chaque lot pour alimenter la barre de progression côté front.
    """
    objs, failed = [], []
    try:
        total = pdf.page_count(tmp_path)
        first, last = _parse_pages(spec, total)
        page = first
        while page <= last:
            blast = min(page + batch - 1, last)
            try:
                imgs = pdf.render_pages(tmp_path, page, blast, dpi=dpi)
                objs.extend(extract.extract_objects(s["provider"], s["extract_model"], imgs))
            except Exception as e:
                failed.append({"pages": [page, blast], "error": f"{type(e).__name__}: {e}"})
            page = blast + 1
            with _JOBS_LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id]["done"] += 1
        if not objs:
            detail = ", ".join(f"{b['pages'][0]}-{b['pages'][1]}" for b in failed)
            msg = "aucun objet extrait" + (f" (échecs sur les pages {detail})" if detail else "")
            with _JOBS_LOCK:
                _JOBS[job_id].update(status="error", error=msg, failed=failed)
            return
        cards_mod.canonicalize_labels(objs)  # uniformise les libellés entre lots
        cards = cards_mod.expand_all(objs)
        decks = cards_mod.default_deck_map(cards)
        STATE["gen"] = {"cards": [c.model_dump() for c in cards], "decks": decks}
        _save_gen(STATE["gen"])  # persiste pour survivre à un redémarrage
        suggestion = {"annee": "", "cours": ""}
        try:
            sug = extract.suggest_taxonomy(s["provider"], s["extract_model"], objs)
            suggestion = {"annee": sug.annee, "cours": sug.cours}
        except Exception:
            pass
        result = {
            "objects": len(objs), "cards": len(cards),
            "by_type": dict(Counter(o.type.value for o in objs)),
            "pages": [first, last, total], "decks": decks,
            "suggestion": suggestion, "taxonomy": _taxonomy(_sapio_leaf_decks()),
            "failed": failed,
        }
        with _JOBS_LOCK:
            _JOBS[job_id].update(status="done", result=result)
    except Exception as e:
        with _JOBS_LOCK:
            _JOBS[job_id].update(status="error", error=f"{type(e).__name__}: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def create_api(config: dict) -> Flask:
    app = Flask(__name__, static_folder=None)
    settings.load()
    settings.apply()  # configure la collection d'après les préférences

    # ---- API ----
    @app.get("/api/decks")
    def api_decks():
        # Forêt des decks Sapio (Année › Cours › Chapitre › Partie), sans racine
        # artificielle. Compteurs plafonnés (limites quotidiennes d'Anki).
        names = _all_deck_names(_sapio_leaf_decks())
        stats = anki.deck_stats_map()

        def cnt(full: str) -> int:
            st = stats.get(full, {})
            return st.get("new", 0) + st.get("learn", 0) + st.get("review", 0)

        nodes: dict[str, dict] = {}
        roots: list[dict] = []
        for n in names:
            parts = n.split("::")
            for i in range(len(parts)):
                full = "::".join(parts[: i + 1])
                if full not in nodes:
                    node = {"name": parts[i], "full": full, "count": cnt(full), "children": []}
                    nodes[full] = node
                    (nodes["::".join(parts[:i])]["children"] if i > 0 else roots).append(node)
        return jsonify({"name": "", "full": "", "count": sum(r["count"] for r in roots), "children": roots})

    @app.get("/api/taxonomy")
    def api_taxonomy():
        return jsonify(_taxonomy(_sapio_leaf_decks()))

    @app.get("/api/cards")
    def api_cards():
        deck = request.args.get("deck")
        if deck:
            # Plafonner comme Anki : nouvelles / apprentissage / révisions du jour.
            st = anki.deck_stats_map().get(deck, {})
            n_new, n_learn, n_rev = st.get("new", 0), st.get("learn", 0), st.get("review", 0)
            due = anki.find_cards(f'deck:"{deck}" is:due')[: n_learn + n_rev]
            new = anki.find_cards(f'deck:"{deck}" is:new')[: n_new]
            ids = (due + new)[: config["limit"]]
        else:
            ids = anki.find_cards(config["query"])[: config["limit"]]
        infos = {i["cardId"]: i for i in anki.cards_info(ids)}
        raw = []
        for cid in ids:
            f = anki.fields_of(infos[cid]) if cid in infos else {}
            raw.append({
                "card_id": cid, "mode": f.get("Mode", ""), "type": f.get("Type", ""),
                "importance": f.get("Importance", ""), "consigne": f.get("Consigne", ""),
                "contexte": f.get("Contexte", ""), "attendu": f.get("Attendu", ""),
                "titre": f.get("Titre", ""), "lecon": f.get("Lecon", ""),
            })
        raw.sort(key=lambda c: (_MODE_RANK.get(c["mode"], len(PHASES)),))
        cards = [{**c, "numero": n} for n, c in enumerate(raw, start=1)]
        STATE["cards"] = cards
        phases = []
        for title, modes in PHASES:
            sel = [_public_card(c) for c in cards if c["mode"] in modes]
            if sel:
                phases.append({"title": title, "cards": sel})
        return jsonify({"count": len(cards), "phases": phases})

    @app.post("/api/transcribe")
    def api_transcribe():
        cards = STATE.get("cards") or []
        images = [f.read() for f in request.files.getlist("photos") if f.filename]
        if not cards or not images:
            return jsonify({"error": "cartes ou photos manquantes"}), 400
        STATE["images"] = images
        s = settings.get()
        batch = review.transcribe_batch(s["provider"], s["review_model"], cards, images)
        by = {t.numero: t for t in batch.transcriptions}
        out = []
        for c in cards:
            t = by.get(c["numero"])
            out.append({
                "numero": c["numero"], "titre": c["titre"], "type": c["type"],
                "color": _TYPE_COLOR.get(c["type"], ""), "mode": c["mode"],
                "traitee": bool(t.traitee) if t else False,
                "lecture": t.lecture if t else "", "confiance": t.confiance if t else "",
                "doutes": [d.model_dump() for d in t.doutes] if t else [],
            })
        return jsonify({"transcriptions": out})

    @app.post("/api/grade")
    def api_grade():
        cards = {c["numero"]: c for c in STATE.get("cards") or []}
        items = (request.get_json(silent=True) or {}).get("items", [])
        confirmed = [
            {**cards[i["numero"]], "lecture": i.get("lecture", "")}
            for i in items if i.get("traitee") and i["numero"] in cards
        ]
        gmap = {}
        if confirmed:
            s = settings.get()
            batch = review.grade_batch(s["provider"], s["review_model"], confirmed)
            gmap = {g.numero: g for g in batch.grades}
        treated = {c["numero"] for c in confirmed}
        results = []
        for num, c in cards.items():
            g = gmap.get(num)
            results.append({
                "numero": num, "card_id": c["card_id"], "titre": c["titre"],
                "type": c["type"], "color": _TYPE_COLOR.get(c["type"], ""), "mode": c["mode"],
                "graded": num in treated and g is not None,
                "feedback": g.feedback if g else "", "note": g.note if g else "",
                "justification": g.justification if g else "",
            })
        STATE["results"] = results
        return jsonify({"results": results})

    @app.post("/api/commit")
    def api_commit():
        cards = {c["numero"]: c for c in STATE.get("cards") or []}
        notes = (request.get_json(silent=True) or {}).get("notes", [])
        sent = 0
        for it in notes:
            num, note = it.get("numero"), it.get("note")
            if note not in review.RATING_TO_EASE or num not in cards:
                continue
            ease = review.RATING_TO_EASE[note]
            c = cards[num]
            try:
                anki.answer_card(int(c["card_id"]), ease)
            except anki.AnkiError:
                pass
            history.append(config["history"], {
                "card_id": c["card_id"], "lecon": c.get("lecon", ""),
                "titre": c.get("titre", ""), "mode": c.get("mode", ""),
                "importance": c.get("importance", ""), "note": note, "ease": ease,
            })
            sent += 1
        try:
            bilan.build(history.load(config["history"]), config["bilan_out"])
        except Exception:
            pass
        synced = _autosync()
        return jsonify({"sent": sent, "synced": synced})

    @app.post("/api/sync")
    def api_sync():
        direction = (request.get_json(silent=True) or {}).get("direction")
        try:
            return jsonify({"status": anki.sync(direction)})
        except anki.AnkiError as e:
            return jsonify({"error": str(e)})

    def _autosync() -> bool:
        try:
            anki.sync()
            return True
        except Exception:
            return False

    @app.get("/api/bilan.pdf")
    def api_bilan():
        p = Path(config["bilan_out"])
        return send_file(p) if p.is_file() else ("", 404)

    # ---- Paramètres (préférences non sensibles uniquement) ----
    @app.get("/api/settings")
    def api_settings_get():
        # Les secrets ne transitent JAMAIS : on n'expose que leur présence.
        return jsonify({"settings": settings.get(), "secrets": settings.secret_status()})

    @app.post("/api/settings")
    def api_settings_set():
        body = request.get_json(silent=True) or {}
        # On ignore silencieusement toute clé hors préférences (secrets refusés).
        try:
            saved = settings.save(body)
        except anki.AnkiError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"settings": saved, "secrets": settings.secret_status()})

    # ---- Génération de cartes depuis un poly PDF ----
    # On lance la lecture en tâche de fond et on rend tout de suite un identifiant
    # de job. Le front interroge /api/generate/status pour suivre l'avancement et
    # récupérer le résultat. Évite le timeout du reverse-proxy sur un gros poly.
    @app.post("/api/generate")
    def api_generate():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "PDF manquant"}), 400
        spec = request.form.get("pages", "all")
        s = settings.get()
        dpi = s.get("dpi", 150)
        # Découpage automatique en lots de pages : un gros poly dépasse le budget
        # de sortie d'un seul appel. On traite par tranches et on accumule.
        batch = int(os.environ.get("SAPIO_BATCH_PAGES", 0) or 0) or _GEN_BATCH_PAGES
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            f.save(tmp.name)
            tmp.close()
            total = pdf.page_count(tmp.name)
            first, last = _parse_pages(spec, total)
        except Exception as e:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
        n_batches = (last - first) // batch + 1 if last >= first else 0
        job_id = uuid.uuid4().hex
        with _JOBS_LOCK:
            # purge des vieux jobs terminés pour ne pas accumuler en mémoire
            stale = [k for k, v in _JOBS.items() if v["status"] != "running"]
            for k in stale[:-10]:
                _JOBS.pop(k, None)
            _JOBS[job_id] = {"status": "running", "done": 0, "total": n_batches}
        threading.Thread(
            target=_run_generation,
            args=(job_id, tmp.name, spec, s, batch, dpi),
            daemon=True,
        ).start()
        return jsonify({"job": job_id, "total": n_batches})

    @app.get("/api/generate/status/<job_id>")
    def api_generate_status(job_id):
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            job = dict(job) if job else None
        if not job:
            return jsonify({"error": "job inconnu"}), 404
        payload = {"status": job["status"], "done": job["done"], "total": job["total"]}
        if job["status"] == "done":
            payload.update(job["result"])
        elif job["status"] == "error":
            payload["error"] = job.get("error", "échec de la génération")
            if job.get("failed"):
                payload["failed"] = job["failed"]
        resp = jsonify(payload)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/import")
    def api_import():
        gen = STATE.get("gen") or _load_gen()
        if not gen:
            return jsonify({"error": "rien à importer (génère d'abord)"}), 400
        STATE["gen"] = gen  # repeuple le cache mémoire après un redémarrage
        body = request.get_json(silent=True) or {}
        decks = body.get("decks", gen["decks"])
        annee = (body.get("annee") or "").strip()
        cours = (body.get("cours") or "").strip()
        deck_root = "::".join(p for p in (annee, cours) if p) or "Sapio"
        lookup = cards_mod.deck_lookup(decks)
        notes = [anki.card_to_note(c, deck_root, lookup) for c in gen["cards"]]
        deck_names = sorted({n["deckName"] for n in notes})
        try:
            anki.ensure_model()
            res = anki.add_notes(notes)  # crée les decks au passage
        except anki.AnkiError as e:
            return jsonify({"error": str(e)}), 502
        added = sum(1 for r in res if r is not None)
        # Préinitialisation du niveau de maîtrise, par sous-deck. On regroupe les
        # notes créées par intervalle visé puis on sème la mémoire FSRS. Les
        # doublons (res None) et le niveau « neuf » sont ignorés.
        days_of_deck = {
            f"{deck_root}::{e['deck']}": _MASTERY_DAYS.get((e.get("level") or "neuf").lower(), 0)
            for e in decks
        }
        by_days: dict[int, list] = {}
        for note, nid in zip(notes, res):
            if nid is None:
                continue
            d = days_of_deck.get(note["deckName"], 0)
            if d > 0:
                by_days.setdefault(d, []).append(nid)
        seeded = 0
        for d, nids in by_days.items():
            seeded += anki.seed_memory(anki.card_ids_of_notes(nids), d)
        synced = _autosync()
        return jsonify({
            "added": added, "skipped": len(res) - added, "seeded": seeded,
            "decks": deck_names, "synced": synced,
        })

    # ---- SPA statique (build Vite) ----
    @app.get("/")
    @app.get("/<path:path>")
    def spa(path: str = ""):
        if path.startswith("api/"):
            return ("", 404)
        target = DIST / path
        if path and target.is_file():
            return send_from_directory(DIST, path)
        index = DIST / "index.html"
        if index.is_file():
            return send_from_directory(DIST, "index.html")
        return (
            "<h1>Front non construit</h1><p>Lance <code>npm run build</code> dans "
            "<code>sapio/frontend</code>, ou <code>npm run dev</code> pour le mode dev.</p>",
            200,
        )

    return app
