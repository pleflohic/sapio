# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application web locale de révision (spec_sapio.md §6).

Flux en 3 temps (« une seule capture ») :
1. Cartes du jour numérotées → l'élève travaille tout sur papier (avec les numéros)
   → une capture (1+ photos).
2. Le modèle TRANSCRIT chaque réponse en LaTeX ; l'élève VALIDE ou CORRIGE dans un
   éditeur (aperçu live). On ne note jamais sur une lecture non confirmée.
3. Le modèle NOTE les transcriptions validées (texte seul) → page de résultats →
   validation (FSRS + historique + bilan).

App mono-utilisateur locale : l'état de session vit dans un global.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for

from . import anki_backend as anki, bilan, history, review

STATE: dict = {}  # {cards, images, trans, results}

# Phases de révision, du superficiel au profond (option A : affichage guidé,
# une seule photo à la fin). Faire `enoncer` en premier évite la fuite de
# contexte (on restitue de mémoire avant que les phases suivantes ne montrent
# l'énoncé de référence).
PHASES = [
    ("Énoncés", {"enoncer"}),
    ("Exemples & contre-exemples", {"exemple", "contre_exemple"}),
    ("Démonstrations", {"preuve"}),
    ("Exercices", {"resoudre"}),
]
_MODE_RANK = {m: i for i, (_, modes) in enumerate(PHASES) for m in modes}

# Code couleur par type (clé = libellé français du champ Type) → classe CSS.
_TYPE_COLOR = {
    "Définition": "t-def",   # vert
    "Proposition": "t-prop",  # bleu
    "Lemme": "t-prop",        # bleu
    "Théorème": "t-theo",     # rouge
    "Exercice": "t-exo",      # ambre
}

_CSS = """
:root { --bg:#faf8f3; --ink:#1a1a1a; --accent:#9a3b2e; --muted:#8a8a8a; --ok:#2e7d52; }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--ink);
  font-family:Georgia,serif; line-height:1.55; }
.wrap { max-width:780px; margin:0 auto; padding:1.4rem 1.2rem 4rem; }
h1 { font-size:1.5rem; margin:.2rem 0 1rem; }
.mode { font-variant:small-caps; letter-spacing:.05em; color:var(--accent); font-size:.8rem; }
.card { background:#fff; border:1px solid #eee; border-radius:10px; padding:1rem 1.1rem; margin:.9rem 0; }
.num { display:inline-block; min-width:1.8em; height:1.8em; line-height:1.8em; text-align:center;
  background:var(--accent); color:#fff; border-radius:50%; font-weight:bold; margin-right:.5em; }
.consigne { font-weight:bold; margin-top:.4rem; } .feedback { margin:.5rem 0; }
.ctx { margin-top:.5rem; padding:.5rem .7rem; background:#f0ece2; border-radius:6px; font-size:.92rem; }
.src { color:var(--muted); font-size:.8rem; } .doute { color:var(--accent); font-size:.9rem; }
.conf-haute { color:var(--ok); } .conf-moyenne, .conf-faible { color:var(--accent); }
textarea.tex { width:100%; font-family:ui-monospace,monospace; font-size:.9rem; padding:.5rem;
  border:1px solid #ddd; border-radius:6px; } .preview { background:#f6f3ec; border-radius:6px;
  padding:.5rem .7rem; margin-top:.4rem; min-height:1.6em; } .notes label { margin-right:1rem; }
button { background:var(--accent); color:#fff; border:0; border-radius:8px; padding:.7rem 1.4rem;
  font-size:1rem; cursor:pointer; } .btn { text-decoration:none; } .muted { color:var(--muted); }
.phase-title { font-size:1.15rem; margin:.2rem 0 .6rem; }
.nav { position:sticky; bottom:0; background:var(--bg); padding:.8rem 0; margin-top:1rem;
  display:flex; gap:.6rem; border-top:1px solid #e6e0d4; }
.nav button[disabled] { opacity:.35; cursor:default; }
#plabel { font-size:.85rem; margin-bottom:.6rem; }
.t-def  { border-left:6px solid #2e7d52; } .t-def  .mode { color:#2e7d52; }
.t-prop { border-left:6px solid #2b6cb0; } .t-prop .mode { color:#2b6cb0; }
.t-theo { border-left:6px solid #c0392b; } .t-theo .mode { color:#c0392b; }
.t-exo  { border-left:6px solid #b8860b; } .t-exo  .mode { color:#b8860b; }
"""

_HEAD = """<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<script>MathJax={tex:{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']]}};</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>""" + _CSS + "</style>"

INDEX = """<!doctype html><html><head>""" + _HEAD + """<title>Cartes du jour</title></head>
<body><div class="wrap"><h1>Cartes du jour — {{cards|length}}</h1>
{% if not cards %}<p class="muted">Rien à réviser aujourd'hui 🎉</p>{% else %}
<div id="plabel" class="muted"></div>

{% for p in phases %}
<section class="step" data-i="{{loop.index0}}" hidden>
  <h2 class="phase-title">{{p.title}}</h2>
  <p class="muted">Rédige sur papier chaque réponse en écrivant son <b>numéro</b> à côté.</p>
  {% for c in p.cards %}<div class="card {{c.css}}">
    <div class="mode"><b>{{c.type}}</b> · {{c.mode}} · {{c.importance}}</div>
    <div class="consigne"><span class="num">{{c.numero}}</span>{{c.consigne|safe}}</div>
    {% if c.contexte %}<div class="ctx"><i>Énoncé de référence :</i><br>{{c.contexte|safe}}</div>{% endif %}
    <div class="src">{{c.titre|safe}} — {{c.lecon}}</div></div>{% endfor %}
</section>
{% endfor %}

<section class="step" data-i="{{phases|length}}" hidden>
  <h2 class="phase-title">Photo de ta copie</h2>
  <p class="muted">Une fois tout rédigé, photographie l'ensemble (1+ photos).</p>
  <form method="post" action="{{url_for('transcribe')}}" enctype="multipart/form-data">
    <p><input type="file" name="photos" accept="image/*" capture="environment" multiple required></p>
    <button type="submit">Lire ma copie</button>
  </form>
</section>

<div class="nav">
  <button type="button" id="prev">← Précédent</button>
  <button type="button" id="next">Suivant →</button>
</div>

<script>
var steps=[].slice.call(document.querySelectorAll('.step')), i=0;
function show(k){ i=Math.max(0,Math.min(steps.length-1,k));
  steps.forEach(function(s,j){ s.hidden = (j!==i); });
  document.getElementById('plabel').textContent='Étape '+(i+1)+' / '+steps.length;
  document.getElementById('prev').disabled = (i===0);
  document.getElementById('next').disabled = (i===steps.length-1);
  if(window.MathJax&&MathJax.typesetPromise){MathJax.typesetPromise([steps[i]]);}
  window.scrollTo(0,0);
}
document.getElementById('next').onclick=function(){show(i+1);};
document.getElementById('prev').onclick=function(){show(i-1);};
show(0);
</script>
{% endif %}</div></body></html>"""

TRANSCRIBE = """<!doctype html><html><head>""" + _HEAD + """<title>Vérifie la lecture</title></head>
<body><div class="wrap"><h1>Vérifie ce que j'ai lu</h1>
<p class="muted">Voici ma transcription de ta copie. Les lectures sûres sont marquées
« probablement OK » : survole-les. Corrige ce qui est faux, puis lance la notation.</p>
<form method="post" action="{{url_for('grade')}}">
{% for c in cards %}{% set t = trans[loop.index0] %}
<div class="card {{c.css}}"><div class="mode"><b>{{c.type}}</b> · {{c.mode}} · {{c.importance}}</div>
<div class="consigne"><span class="num">{{c.numero}}</span>{{c.titre|safe}}</div>
{% if not t.traitee %}
  <p class="muted">Non traitée — laissée intacte.</p>
  <input type="hidden" name="traitee_{{c.numero}}" value="0">
{% else %}
  <p class="conf-{{t.confiance}}">lecture : {{t.confiance}}{% if t.confiance=='haute' %} ✓ probablement OK{% endif %}</p>
  {% for d in t.doutes %}<p class="doute">⚠️ {{d.passage}} — {{d.question}}</p>{% endfor %}
  <textarea class="tex" id="tex_{{c.numero}}" data-num="{{c.numero}}" name="lecture_{{c.numero}}" rows="6">{{t.lecture}}</textarea>
  <div class="preview" id="prev_{{c.numero}}"></div>
  <input type="hidden" name="traitee_{{c.numero}}" value="1">
  <input type="hidden" name="card_{{c.numero}}" value="{{c.card_id}}">
{% endif %}</div>{% endfor %}
<button type="submit">Valider la lecture et noter</button></form>
<script>
function prev(n){var t=document.getElementById('tex_'+n),p=document.getElementById('prev_'+n);
 if(!t||!p)return;p.textContent=t.value;if(window.MathJax&&MathJax.typesetPromise)MathJax.typesetPromise([p]);}
document.addEventListener('DOMContentLoaded',function(){
 document.querySelectorAll('textarea.tex').forEach(function(t){var n=t.dataset.num;
  t.addEventListener('input',function(){prev(n);});prev(n);});});
</script></div></body></html>"""

RESULTS = """<!doctype html><html><head>""" + _HEAD + """<title>Résultats</title></head>
<body><div class="wrap"><h1>Résultats</h1>
<form method="post" action="{{url_for('commit')}}">
{% for r in results %}<div class="card {{r.css}}"><div class="mode"><b>{{r.type}}</b> · {{r.mode}} · {{r.importance}}</div>
<div class="consigne"><span class="num">{{r.numero}}</span>{{r.titre|safe}}</div>
{% if not r.graded %}<p class="muted">Non traitée — laissée intacte.</p>
{% else %}<div class="feedback">{{r.feedback|safe}}</div>
<div class="notes">Note :
{% for n in ['again','hard','good','easy'] %}<label><input type="radio" name="note_{{r.numero}}"
 value="{{n}}"{% if r.note==n %} checked{% endif %}>{{n}}</label>{% endfor %}</div>
<p class="src">{{r.justification}}</p>
<input type="hidden" name="card_{{r.numero}}" value="{{r.card_id}}">{% endif %}
</div>{% endfor %}
<button type="submit">Valider la session</button></form></div></body></html>"""

DONE = """<!doctype html><html><head>""" + _HEAD + """<title>Session validée</title></head>
<body><div class="wrap"><h1>Session validée ✓</h1>
<p>{{n}} carte(s) envoyée(s) à Anki (FSRS replanifie).</p>
<p><a class="btn" href="{{url_for('bilan_pdf')}}">Voir le bilan PDF</a></p>
<p><a href="{{url_for('index')}}">↺ Retour aux cartes du jour</a></p></div></body></html>"""


def create_app(config: dict) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        ids = anki.find_cards(config["query"], config["url"])[: config["limit"]]
        infos = {i["cardId"]: i for i in anki.cards_info(ids, config["url"])}
        raw = []
        for cid in ids:
            f = anki.fields_of(infos[cid]) if cid in infos else {}
            raw.append({
                "card_id": cid, "mode": f.get("Mode", ""),
                "type": f.get("Type", ""), "css": _TYPE_COLOR.get(f.get("Type", ""), ""),
                "contexte": f.get("Contexte", ""),
                "consigne": f.get("Consigne", ""), "attendu": f.get("Attendu", ""),
                "titre": f.get("Titre", ""), "lecon": f.get("Lecon", ""),
                "importance": f.get("Importance", ""),
            })
        # Trier par phase (énoncer d'abord…) puis numéroter dans cet ordre, pour
        # que l'affichage phasé et les numéros sur la copie coïncident.
        raw.sort(key=lambda c: (_MODE_RANK.get(c["mode"], len(PHASES)),))
        cards = [{**c, "numero": n} for n, c in enumerate(raw, start=1)]
        STATE["cards"] = cards
        # Regrouper en phases non vides (dans l'ordre PHASES).
        phases = []
        for title, modes in PHASES:
            sel = [c for c in cards if c["mode"] in modes]
            if sel:
                phases.append({"title": title, "cards": sel})
        return render_template_string(INDEX, cards=cards, phases=phases)

    @app.post("/transcribe")
    def transcribe():
        cards = STATE.get("cards") or []
        images = [f.read() for f in request.files.getlist("photos") if f.filename]
        if not cards or not images:
            return redirect(url_for("index"))
        STATE["images"] = images
        batch = review.transcribe_batch(config["provider"], config["model"], cards, images)
        by_num = {t.numero: t for t in batch.transcriptions}
        trans = [
            (by_num.get(c["numero"]) or _absent_trans(c["numero"])).model_dump() for c in cards
        ]
        STATE["trans"] = trans
        return render_template_string(TRANSCRIBE, cards=cards, trans=trans)

    @app.post("/grade")
    def grade():
        cards = STATE.get("cards") or []
        by_num = {c["numero"]: c for c in cards}
        confirmed = []
        for c in cards:
            if request.form.get(f"traitee_{c['numero']}") == "1":
                lecture = request.form.get(f"lecture_{c['numero']}", "")
                confirmed.append({**c, "lecture": lecture})
        gmap = {}
        if confirmed:
            batch = review.grade_batch(config["provider"], config["model"], confirmed)
            gmap = {g.numero: g for g in batch.grades}
        results = []
        treated = {c["numero"] for c in confirmed}
        for c in cards:
            if c["numero"] in treated and c["numero"] in gmap:
                g = gmap[c["numero"]]
                results.append({**c, "graded": True, "feedback": g.feedback,
                                "note": g.note, "justification": g.justification})
            else:
                results.append({**c, "graded": False})
        STATE["results"] = results
        return render_template_string(RESULTS, results=results)

    @app.post("/commit")
    def commit():
        cards = {c["numero"]: c for c in STATE.get("cards") or []}
        sent = 0
        for r in STATE.get("results") or []:
            note = request.form.get(f"note_{r['numero']}")
            cid = request.form.get(f"card_{r['numero']}")
            if not note or not cid or note not in review.RATING_TO_EASE:
                continue
            ease = review.RATING_TO_EASE[note]
            try:
                anki.answer_card(int(cid), ease, config["url"])
            except anki.AnkiConnectError:
                pass
            c = cards.get(r["numero"], r)
            history.append(config["history"], {
                "card_id": int(cid), "lecon": c.get("lecon", ""), "titre": c.get("titre", ""),
                "mode": c.get("mode", ""), "importance": c.get("importance", ""),
                "note": note, "ease": ease,
            })
            sent += 1
        try:
            bilan.build(history.load(config["history"]), config["bilan_out"])
        except Exception:
            pass
        return render_template_string(DONE, n=sent)

    @app.get("/bilan.pdf")
    def bilan_pdf():
        p = Path(config["bilan_out"])
        if not p.is_file():
            abort(404)
        return send_file(p)

    return app


def _absent_trans(numero: int):
    from .models import CardTranscription

    return CardTranscription(numero=numero, traitee=False, lecture="", confiance="", doutes=[])
