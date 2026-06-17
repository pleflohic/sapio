# SPDX-License-Identifier: AGPL-3.0-or-later
"""Préférences applicatives (source unique, éditables depuis l'app).

Option « stricte » : ce module ne gère QUE des réglages non sensibles
(provider, modèles, DPI, chemin de collection). Les SECRETS (clés API,
identifiants AnkiWeb) ne passent jamais par ici ni par HTTP : ils restent dans
l'environnement / le `.env`. On expose seulement leur *présence* (✓/✗).

Fichier : $SAPIO_CONFIG_DIR (ou ~/.config/sapio)/settings.json, créé à la
première sauvegarde (chmod 600). Amorcé depuis l'environnement → rétro-compat
avec un `.env` existant.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from . import anki_backend as anki

_LOCK = threading.Lock()
_CACHE: dict | None = None
_PREF_KEYS = ("provider", "extract_model", "review_model", "dpi", "collection")


def _config_dir() -> Path:
    base = os.environ.get("SAPIO_CONFIG_DIR")
    if base:
        return Path(base)
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "sapio"


def _path() -> Path:
    return _config_dir() / "settings.json"


def _defaults() -> dict:
    return {
        "provider": os.environ.get("SAPIO_PROVIDER", "anthropic"),
        "extract_model": os.environ.get("SAPIO_EXTRACT_MODEL")
        or os.environ.get("SAPIO_MODEL")
        or "claude-sonnet-4-6",
        "review_model": os.environ.get("SAPIO_REVIEW_MODEL")
        or os.environ.get("SAPIO_MODEL")
        or "claude-opus-4-8",
        "dpi": int(os.environ.get("SAPIO_DPI", 150)),
        "collection": os.environ.get("SAPIO_COLLECTION", ""),
    }


def load() -> dict:
    global _CACHE
    s = _defaults()
    p = _path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            s.update({k: v for k, v in data.items() if k in _PREF_KEYS})
        except Exception:
            pass
    _CACHE = s
    return s


def get() -> dict:
    return _CACHE if _CACHE is not None else load()


def apply() -> None:
    """Applique les préférences (ouvre/configure la collection)."""
    anki.configure(get().get("collection", ""))


def save(updates: dict) -> dict:
    with _LOCK:
        s = get().copy()
        for k in _PREF_KEYS:
            if k in updates and updates[k] is not None:
                s[k] = updates[k]
        try:
            s["dpi"] = int(s["dpi"])
        except Exception:
            s["dpi"] = 150
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        p = _path()
        p.write_text(json.dumps({k: s[k] for k in _PREF_KEYS}, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        global _CACHE
        _CACHE = s
    apply()
    return s


def secret_status() -> dict:
    """Présence (et non valeur) des secrets, lus dans l'environnement uniquement."""
    return {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
        "ankiweb": bool(os.environ.get("ANKIWEB_USERNAME") and os.environ.get("ANKIWEB_PASSWORD")),
    }
