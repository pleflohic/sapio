# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bilan de performance cumulatif (spec_sapio.md §8).

Lit l'historique des révisions et produit un fichier LaTeX compilé en PDF :
vue d'ensemble, performance par leçon et par mode, points à retravailler.
Généré automatiquement en fin de session (et à la demande via `sapio bilan`).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

_SPECIALS = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}"}


def _esc(s: str) -> str:
    return "".join(_SPECIALS.get(c, c) for c in str(s))


def _render_tex(records: list[dict]) -> str:
    total = len(records)
    notes = Counter(r["note"] for r in records)
    # Dernière note par carte → points fragiles.
    latest: dict = {}
    for r in records:
        latest[r["card_id"]] = r
    fragiles = [r for r in latest.values() if r["note"] in ("again", "hard")]

    par_lecon: dict = defaultdict(Counter)
    for r in records:
        par_lecon[r.get("lecon") or "—"][r["note"]] += 1

    def _row_notes(c: Counter) -> str:
        return " / ".join(f"{c.get(n, 0)}" for n in ("again", "hard", "good", "easy"))

    lignes_lecon = "\n".join(
        rf"{_esc(lec)} & {_row_notes(c)} \\" for lec, c in sorted(par_lecon.items())
    )
    lignes_fragiles = (
        "\n".join(
            rf"{_esc(r['titre'])} & {_esc(r['mode'])} & {r['note']} \\" for r in fragiles
        )
        or r"\multicolumn{3}{l}{\emph{Aucun point fragile.}} \\"
    )

    return rf"""\documentclass[11pt]{{article}}
\usepackage[T1]{{fontenc}}
\usepackage[utf8]{{inputenc}}
\usepackage[margin=2.2cm]{{geometry}}
\usepackage{{booktabs}}
\setlength{{\parindent}}{{0pt}}
\begin{{document}}

{{\Large\bfseries Bilan de révision --- Sapio}}\\[2pt]
{date.today().isoformat()} \quad\textbullet\quad {total} restitution(s) évaluée(s)

\bigskip
\textbf{{Vue d'ensemble.}} Again : {notes.get('again',0)} \quad
Hard : {notes.get('hard',0)} \quad Good : {notes.get('good',0)} \quad
Easy : {notes.get('easy',0)}.

\bigskip
\textbf{{Par leçon}} (again / hard / good / easy)

\begin{{tabular}}{{lc}}
\toprule
Leçon & A / H / G / E \\
\midrule
{lignes_lecon}
\bottomrule
\end{{tabular}}

\bigskip
\textbf{{À retravailler}} (dernière restitution Again ou Hard)

\begin{{tabular}}{{lll}}
\toprule
Titre & Mode & Dernière note \\
\midrule
{lignes_fragiles}
\bottomrule
\end{{tabular}}

\end{{document}}
"""


def build(records: list[dict], out_pdf: str | Path) -> Path:
    """Génère le PDF du bilan. Renvoie le chemin du PDF produit."""
    out_pdf = Path(out_pdf).resolve()
    if not shutil.which("pdflatex"):
        raise RuntimeError("pdflatex introuvable (installe une distribution LaTeX).")
    tex = _render_tex(records)
    with tempfile.TemporaryDirectory() as d:
        tex_path = Path(d) / "bilan.tex"
        tex_path.write_text(tex, encoding="utf-8")
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "bilan.tex"],
            cwd=d, capture_output=True, text=True,
        )
        produced = Path(d) / "bilan.pdf"
        if not produced.is_file():
            raise RuntimeError("Échec de compilation LaTeX :\n" + proc.stdout[-1500:])
        shutil.copyfile(produced, out_pdf)
    return out_pdf
