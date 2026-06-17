# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rendu des pages d'un poly PDF en images PNG.

Le corps mathématique d'un poly LaTeX ne s'extrait pas proprement en texte
(pdftotext ne rend que la table des matières) ; on lit donc les pages en
vision. Voir spec_sapio.md §5.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def page_count(pdf_path: str | Path) -> int:
    """Nombre de pages du PDF (via pdfinfo)."""
    out = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("pdfinfo n'a pas renvoyé de nombre de pages")


def render_pages(
    pdf_path: str | Path, first: int, last: int, dpi: int = 150
) -> list[tuple[int, bytes]]:
    """Rend les pages [first, last] en PNG.

    Retourne une liste de (numéro_de_page, octets_png), triée par page.
    """
    with tempfile.TemporaryDirectory() as d:
        prefix = os.path.join(d, "page")
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-f",
                str(first),
                "-l",
                str(last),
                str(pdf_path),
                prefix,
            ],
            check=True,
        )
        pages: list[tuple[int, bytes]] = []
        for f in sorted(Path(d).glob("page-*.png")):
            num = int(f.stem.split("-")[-1])
            pages.append((num, f.read_bytes()))
        return pages
