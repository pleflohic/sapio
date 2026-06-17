# SPDX-License-Identifier: AGPL-3.0-or-later
"""Point d'entrée WSGI pour la production (gunicorn).

    gunicorn app.wsgi:app --bind 127.0.0.1:5000

Les secrets sont lus dans l'environnement / `.env` ; les préférences
(provider, modèles, DPI, collection) dans ~/.config/sapio/settings.json,
éditables depuis l'onglet Paramètres. Voir le README.

⚠️  Aucune authentification intégrée : ne jamais exposer publiquement sans
placer toute l'app derrière une couche d'auth (ex. Cloudflare Access) + HTTPS.
"""

from __future__ import annotations

import os

from .api import create_api
from .cli import _load_dotenv

_load_dotenv()  # amorce l'environnement depuis .env si présent

# Réglages opérationnels (les prefs viennent de settings.json via create_api).
app = create_api(
    {
        "query": os.environ.get("SAPIO_QUERY", "deck:*::* is:due"),
        "limit": int(os.environ.get("SAPIO_LIMIT", 20)),
        "history": os.environ.get("SAPIO_HISTORY", "history.json"),
        "bilan_out": os.environ.get("SAPIO_BILAN", "bilan.pdf"),
    }
)
