# Sapio

**Bridge the power of Anki and AI.**

Sapio branche [Anki](https://apps.ankiweb.net/) sur Claude pour la **révision
active** : il génère des *cartes de restitution* à partir d'un poly PDF, te fait
rédiger tes réponses **à la main**, lit et corrige ta copie photographiée, puis
laisse **FSRS** (l'algorithme de répétition espacée d'Anki) replanifier. Pensé
pour un cours exigeant (type prépa agrég), mais généraliste.

```
poly.pdf ──[vision]──> objets de cours ──[expansion graduée]──> cartes Anki
                                                                    │
révision : tu rédiges sur papier ─> photo ─> [transcription] ─> tu valides
                                  ─> [notation vs attendu] ─> bouton FSRS ─> bilan PDF
```

## Architecture

- **Cœur** : la **bibliothèque officielle `anki`** (collection, FSRS, sync
  AnkiWeb). Pas besoin d'Anki desktop ni d'AnkiConnect — Sapio ouvre directement
  ta collection `.anki2`. C'est « juste un serveur web ».
- **API** : Flask JSON (`sapio/api.py`).
- **Front** : SPA React + Vite + TypeScript (`sapio/frontend/`), servie par Flask
  (même origine, pas de CORS).
- **IA** : Anthropic (Claude) ou OpenRouter, un modèle par étape (extraction
  économique, notation de pointe).

> Sapio importe la bibliothèque `anki`, sous **AGPL-3.0** → Sapio est lui-même
> distribué sous **AGPL-3.0** (voir `LICENSE`).

## Prérequis

- Python ≥ 3.10
- Node ≥ 18 (build du front)
- `pdftoppm` / `pdfinfo` (paquet **poppler-utils**) — rendu des pages PDF
- `pdflatex` (**TeX Live**) — bilan PDF (facultatif)
- Une collection Anki (`collection.anki2`). Sur un serveur neuf, on peut
  l'amorcer par une première synchro descendante depuis AnkiWeb.

## Installation

```bash
git clone <ton-fork> sapio && cd sapio
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                  # + ".[prod]" pour gunicorn

# Front :
cd sapio/frontend
npm install && npm run build      # produit sapio/frontend/dist/, servi par Flask
cd ../..
```

## Configuration

Deux endroits, deux rôles **bien séparés** :

### 1. Secrets → `.env` (à la main, jamais via le web)

Copie `.env.example` en `.env` (gitignoré) :

```bash
ANTHROPIC_API_KEY=sk-ant-...
# OPENROUTER_API_KEY=sk-or-...        # si SAPIO_PROVIDER=openrouter
# ANKIWEB_USERNAME=...                # pour la synchro AnkiWeb
# ANKIWEB_PASSWORD=...
```

Par sécurité, les secrets ne sont **jamais** lisibles ni modifiables par HTTP.
L'app vérifie seulement leur présence (✓/✗) dans l'onglet Paramètres.

### 2. Préférences → onglet **Paramètres** (UI) → `~/.config/sapio/settings.json`

Provider, modèle d'extraction, modèle de notation, DPI, **chemin de la
collection**. Modifiables depuis l'app, appliqués à chaud, écrits dans
`~/.config/sapio/settings.json` (créé automatiquement, chmod 600 ;
surchargeable par `SAPIO_CONFIG_DIR`). Au premier lancement, les valeurs sont
amorcées depuis l'environnement / `.env` (rétro-compat).

> ⚠️ N'ouvre pas la même collection que l'app Anki desktop en même temps (ou
> pendant une synchro) : une seule poignée à la fois.

## Lancer

```bash
# Développement :
sapio serve                       # http://localhost:5000 (et accessible sur le LAN)

# Production :
gunicorn sapio.wsgi:app --bind 127.0.0.1:5000
```

Pour le live-reload du front pendant le dev : `npm run dev` dans `sapio/frontend`.

### Flux de révision (3 temps — on ne note jamais une lecture non confirmée)

1. **Cartes du jour** : choisis un deck, les cartes dues s'affichent **numérotées**.
   Tu rédiges tout **sur papier** (avec le numéro), puis tu déposes **une ou
   plusieurs photos** de l'ensemble.
2. **Vérification** : Claude transcrit chaque réponse en LaTeX (aperçu live,
   éditable). Tu corriges ce qui est mal lu et tu valides.
3. **Notation** : Claude note les transcriptions validées contre l'attendu →
   feedback + note ajustable par carte. « Valider » envoie à **FSRS**, journalise
   et régénère le bilan PDF. Les cartes non traitées restent intactes.

### Créer des cartes

Onglet **Créer des cartes** : dépose un poly PDF → Sapio extrait les objets de
cours et génère les cartes → tu ranges en `Année › Cours › Chapitre › Partie`
(Année/Cours suggérés par Claude, choisis parmi les existants ou nouveaux) → import.

## Synchro AnkiWeb

Renseigne `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` : Sapio synchronise au
démarrage et après chaque session (bouton **↻ Sync** sinon). Une **synchro
complète** (conflit) n'est **jamais** résolue automatiquement (risque de perte) —
il faut la déclencher explicitement.

## ⚠️ Sécurité — avant toute exposition publique

Sapio **n'a aucune authentification intégrée**. L'endpoint `/api/generate`
**dépense ton crédit Claude** et `/api/sync` touche ta collection. Avant de
l'exposer (ex. via un tunnel Cloudflare), place **toute l'app** derrière une
couche d'auth (ex. **Cloudflare Access**) + **HTTPS**.

## CLI

Le serveur web est l'interface recommandée, mais tout est aussi scriptable :

```bash
sapio extract poly.pdf --pages 8-15   # poly → objects.json + cards.json + decks.json
sapio push                            # crée le note type + decks, ajoute les notes
sapio review                          # révision en terminal (une photo par carte)
sapio bilan                           # bilan PDF cumulatif depuis history.json
```

## Crédits & mentions légales

Sapio s'appuie sur la **bibliothèque officielle Anki** (© Ankitects Pty Ltd),
distribuée sous AGPL-3.0 — <https://github.com/ankitects/anki>. C'est cette
dépendance qui impose à Sapio la même licence.

« Anki » et « AnkiWeb » sont des marques d'Ankitects Pty Ltd. Sapio est un
projet **indépendant**, sans affiliation ni soutien d'Ankitects.

Sapio étant une application réseau, la **clause réseau de l'AGPL (§13)**
s'applique : toute personne qui l'utilise à distance a le droit d'en obtenir le
code source correspondant. Garder le dépôt public (ou en proposer le source aux
utilisateurs) satisfait cette obligation.

## Licence

[GNU AGPL-3.0-or-later](LICENSE). Le code source de la dépendance Anki est
disponible sur <https://github.com/ankitects/anki>.
