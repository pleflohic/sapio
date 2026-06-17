# SPDX-License-Identifier: AGPL-3.0-or-later
"""Historique cumulatif des révisions.

Stocké localement en JSON (history.json par défaut). Sert de mémoire des
restitutions passées et alimente le bilan PDF (spec_sapio.md §8).

Note d'archi : la spec prévoit à terme de persister cet historique dans le
champ `custom_data` de la carte Anki ; AnkiConnect ne l'expose pas proprement,
donc on commence par un fichier local. À faire évoluer plus tard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def append(path: str | Path, record: dict) -> None:
    p = Path(path)
    data = load(p)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    data.append(record)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))
