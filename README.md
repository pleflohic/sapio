<p align="center">
  <img src="assets/logo.svg" alt="SAPIO" width="420">
</p>

# SAPIO

SAPIO est une application web locale, fondée sur la bibliothèque Anki, dédiée à
l'apprentissage des mathématiques par restitution active (prépa, licence,
agrégation). Elle s'appuie sur un grand modèle de langage (LLM), via une clé API,
pour assurer deux fonctions absentes d'Anki : la génération de cartes à partir
d'un cours et la correction de copies manuscrites. La planification des révisions
reste assurée par Anki.

## Fonctions

Anki permet déjà la révision par restitution active. Deux tâches restent
toutefois à la charge de l'utilisateur.

1. **La fabrication des cartes** à partir d'un polycopié de plusieurs centaines
   de pages, longue à faire manuellement.
2. **L'évaluation de la copie.** Anki ne corrige pas la réponse manuscrite de
   l'utilisateur, il ne connaît que l'évaluation que celui-ci porte sur son
   propre travail, sans garantie qu'elle soit lucide.

## Fonctionnement

1. **Génération des cartes.** Un polycopié (PDF) est déposé dans l'application.
   SAPIO y repère les objets de cours (définitions, théorèmes, propositions,
   lemmes et exercices), évalue l'importance de chacun (central, standard ou
   technique) et en dérive des cartes de restitution. Un résultat donne une
   carte d'énoncé et une carte de démonstration (idée directrice puis preuve
   complète), une définition donne une carte d'énoncé, un exercice donne une
   carte de résolution. Les résultats informels et les exemples ou
   contre-exemples présents dans le polycopié sont traités comme des exercices.
   Les cartes sont rangées par cours et chapitre, puis importées dans Anki.

2. **Révision.** La réponse est rédigée sur papier, de mémoire, puis
   photographiée. SAPIO transmet la photo au modèle via l'API du fournisseur
   configuré. Le modèle transcrit le manuscrit, le compare à la réponse attendue
   et renvoie un retour assorti d'une note. Cette note alimente le bouton FSRS
   d'Anki, qui planifie la suite.

FSRS est l'algorithme de planification d'Anki. Il détermine quand revoir chaque
carte pour une rétention durable. SAPIO se borne à lui fournir une note d'entrée
de meilleure qualité.

## Ce que SAPIO ajoute à Anki

| | Anki seul | Avec SAPIO |
|---|---|---|
| **Création des cartes** | manuelle, fastidieuse | générée depuis le polycopié PDF |
| **Correction de la réponse** | auto-évaluation | copie lue et notée par l'IA contre la réponse attendue |
| **Planification** | FSRS | FSRS (inchangé) |
| **Synchro** | AnkiWeb | AnkiWeb (inchangé) |
| **Suivi** | statistiques Anki | bilan PDF par leçon |

L'interface est épurée et adaptée au mobile (une seule photo de la copie suffit).
SAPIO peut tourner en local sur une machine, ou être hébergé sur un VPS et exposé
derrière un tunnel Cloudflare. Il ne remplace pas Anki, il s'appuie dessus. Les
cartes restent dans la collection de l'utilisateur, planifiées par FSRS et
synchronisées sur AnkiWeb.

## Architecture

Le cœur est la **bibliothèque officielle `anki`** (collection, FSRS, synchro
AnkiWeb). Ni Anki desktop ni AnkiConnect ne sont requis, SAPIO ouvre directement
la collection `.anki2`. Il s'agit pour l'essentiel d'un serveur web.

Les couches sont les suivantes.

1. **API** : Flask en JSON (`app/api.py`).
2. **Front** : une SPA React, Vite et TypeScript (`app/frontend/`), servie par
   Flask sur la même origine (donc sans CORS).
3. **IA** : provider configurable (Anthropic ou OpenRouter), avec un modèle par
   étape. Un modèle économique pour l'extraction (lecture d'imprimé) et un modèle
   de pointe pour la notation (jugement de rigueur sur un manuscrit).

Le package Python s'appelle `app`, et la commande CLI reste `sapio`.

> SAPIO importe la bibliothèque `anki`, sous **AGPL-3.0**. En conséquence SAPIO
> est lui-même distribué sous **AGPL-3.0** (voir `LICENSE`).

## Prérequis

1. Python 3.10 ou plus.
2. Node 18 ou plus (pour le build du front).
3. `pdftoppm` et `pdfinfo` (paquet **poppler-utils**), pour le rendu des pages PDF.
4. `pdflatex` (**TeX Live**), pour le bilan PDF (facultatif).
5. Une collection Anki (`collection.anki2`). Sur un serveur neuf, elle peut être
   amorcée par une première synchro descendante depuis AnkiWeb.

## Installation

```bash
git clone git@github.com:pleflohic/sapio.git && cd sapio
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                  # ajoute ".[prod]" pour gunicorn

# Front :
cd app/frontend
npm install && npm run build      # produit app/frontend/dist/, servi par Flask
cd ../..
```

## Configuration

Deux emplacements distincts, avec deux rôles différents.

### 1. Secrets dans `.env` (édités à la main, jamais par le web)

Copier `.env.example` en `.env` (gitignoré).

```bash
ANTHROPIC_API_KEY=sk-ant-...
# OPENROUTER_API_KEY=sk-or-...        # si SAPIO_PROVIDER=openrouter
# ANKIWEB_USERNAME=...                # pour la synchro AnkiWeb
# ANKIWEB_PASSWORD=...
```

Par mesure de sécurité, les secrets ne sont jamais lisibles ni modifiables par
HTTP. L'application vérifie seulement leur présence (✓ ou ✗) dans l'onglet
Paramètres.

### 2. Préférences dans l'onglet **Paramètres**, écrites dans `~/.config/sapio/settings.json`

On y trouve le provider, le modèle d'extraction, le modèle de notation, le DPI et
le chemin de la collection. Ces réglages sont modifiables depuis l'application et
appliqués à chaud. Le fichier est créé automatiquement (chmod 600, emplacement
modifiable via `SAPIO_CONFIG_DIR`). Au premier lancement, les valeurs sont
amorcées depuis l'environnement et le `.env`, pour la compatibilité avec une
installation existante.

> ⚠️ Ne pas ouvrir la même collection que l'app Anki desktop en même temps (ni
> pendant une synchro). Une seule poignée à la fois.

## Lancer

```bash
# Développement :
sapio serve                       # http://localhost:5000 (et accessible sur le LAN)

# Production :
gunicorn app.wsgi:app --bind 127.0.0.1:5000
```

Pour le rechargement à chaud du front pendant le développement, lancer `npm run
dev` dans `app/frontend`.

### Le flux de révision, en trois temps (une lecture non confirmée n'est jamais notée)

1. **Cartes du jour.** Le choix d'un deck affiche les cartes dues, numérotées. La
   rédaction se fait sur papier (avec le numéro), puis une ou plusieurs photos de
   l'ensemble sont déposées.
2. **Vérification.** Le modèle transcrit chaque réponse en LaTeX (aperçu live et
   éditable). Les erreurs de lecture sont corrigées, puis validées.
3. **Notation.** Le modèle note les transcriptions validées contre la réponse
   attendue, et renvoie un retour ainsi qu'une note ajustable par carte. La
   validation envoie à FSRS, journalise la session et régénère le bilan PDF. Les
   cartes non traitées restent intactes.

### Créer des cartes

Dans l'onglet **Créer des cartes**, un polycopié PDF est déposé. SAPIO en extrait
les objets de cours et génère les cartes, qui sont ensuite rangées en
`Année › Cours › Chapitre › Partie` (l'Année et le Cours sont suggérés par le
modèle, à choisir parmi les existants ou à créer), puis importées. L'import peut
préinitialiser un niveau de maîtrise par sous-deck, ce qui amorce la mémoire FSRS
avec une échéance future.

### Consulter les decks

L'onglet **Decks** affiche la hiérarchie complète `Année › Cours › Chapitre ›
Partie` avec le nombre total de cartes par deck. Un clic sur un deck affiche
toutes ses cartes (consigne, énoncé de référence et réponse attendue).

## Synchro AnkiWeb

Renseigner `ANKIWEB_USERNAME` et `ANKIWEB_PASSWORD`. SAPIO synchronise alors au
démarrage et après chaque session (le bouton **↻ Sync** déclenche aussi une
synchro). Une synchro complète (en cas de conflit) n'est jamais résolue
automatiquement, en raison du risque de perte de données. Elle doit être
déclenchée explicitement.

## Sécurité avant toute exposition publique

SAPIO n'a aucune authentification intégrée. L'endpoint `/api/generate` consomme
du crédit API, et `/api/sync` touche la collection. Avant toute exposition (par
exemple via un tunnel Cloudflare), l'application entière doit être placée derrière
une couche d'authentification (par exemple **Cloudflare Access**) et du **HTTPS**,
avec une clé API dédiée et plafonnée pour le serveur.

## CLI

Le serveur web reste l'interface recommandée, mais tout est aussi scriptable.

```bash
sapio extract poly.pdf --pages 8-15   # poly → objects.json, cards.json, decks.json
sapio push                            # crée le note type et les decks, ajoute les notes
sapio review                          # révision en terminal (une photo par carte)
sapio bilan                           # bilan PDF cumulatif depuis history.json
```

## Crédits et mentions légales

SAPIO s'appuie sur la **bibliothèque officielle Anki** (© Ankitects Pty Ltd),
distribuée sous AGPL-3.0 (<https://github.com/ankitects/anki>). Cette dépendance
impose à SAPIO la même licence.

« Anki » et « AnkiWeb » sont des marques d'Ankitects Pty Ltd. SAPIO est un projet
indépendant, sans affiliation ni soutien d'Ankitects.

SAPIO étant une application réseau, la clause réseau de l'AGPL (§13) s'applique.
Toute personne qui l'utilise à distance a le droit d'en obtenir le code source
correspondant. Garder le dépôt public (ou proposer le source aux utilisateurs)
satisfait cette obligation.

## Licence

[GNU AGPL-3.0-or-later](LICENSE). Le code source de la dépendance Anki est
disponible sur <https://github.com/ankitects/anki>.
