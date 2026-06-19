# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modèles de données partagés entre l'extraction (vision) et l'expansion en cartes.

Deux niveaux :
- `CourseObject` : un objet du cours tel que Claude le lit dans le poly
  (définition, théorème/proposition, lemme), avec son importance.
- `Card` : une carte de restitution prête à être créée dans Anki, produite
  par l'expansion graduée d'un `CourseObject` (voir cards.py).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Importance(str, Enum):
    central = "central"
    standard = "standard"
    technique = "technique"


class ObjectType(str, Enum):
    definition = "definition"
    theoreme = "theoreme"  # résultat majeur, le plus central
    proposition = "proposition"  # important mais moins central qu'un théorème
    lemme = "lemme"  # résultat technique, étape intermédiaire
    exercice = "exercice"  # exercice à savoir résoudre (corrigé = preuve)


class CourseObject(BaseModel):
    """Un objet du cours extrait d'une ou plusieurs pages du poly.

    Les champs textuels non pertinents sont des chaînes vides ("") plutôt
    qu'absents (contrainte des sorties structurées). Le contenu mathématique
    est rendu en LaTeX.
    """

    type: ObjectType
    titre: str
    chapitre: str  # chapitre du poly (ex. « 1. Définition dans le cas positif »)
    lecon: str  # partie/section au sein du chapitre (ex. « 1.2 Définition et unicité »)
    source_ref: str
    importance: Importance
    enonce: str
    preuve: str
    idees_cles: str


class PageBatchExtraction(BaseModel):
    """Ce que Claude renvoie pour un lot de pages."""

    objets: list[CourseObject]


class Card(BaseModel):
    """Une carte de restitution (mode figé à la génération)."""

    mode: str
    type: str  # definition | theoreme | proposition | lemme | exercice
    chapitre: str
    lecon: str
    titre: str
    source_ref: str
    importance: str
    consigne: str
    contexte: str  # énoncé de référence affiché comme contexte (vide pour enoncer/resoudre)
    attendu: str


class Doubt(BaseModel):
    """Un point de la copie illisible/ambigu sur lequel demander confirmation."""

    passage: str  # ce qui est incertain
    question: str  # question précise posée à l'élève


class Evaluation(BaseModel):
    """Résultat de l'évaluation d'une copie manuscrite par le modèle."""

    lecture: str  # ce que le modèle a lu (transcription)
    confiance: str  # "haute" | "moyenne" | "faible"
    doutes: list[Doubt]  # vide si aucun doute décisif
    feedback: str  # retour détaillé affiché à l'élève
    note: str  # "again" | "hard" | "good" | "easy"
    justification: str  # pourquoi ce bouton


# --- Flux web en 3 temps : transcrire (vision) → confirmer/éditer → noter (texte) ---


class CardTranscription(BaseModel):
    """Ce que le modèle a lu sur la copie pour UNE carte (à faire valider)."""

    numero: int  # numéro affiché à l'élève (1-based)
    traitee: bool  # l'élève a-t-il traité cette carte ?
    lecture: str  # transcription LaTeX de ce qui est écrit
    confiance: str  # "haute" | "moyenne" | "faible"
    doutes: list[Doubt]  # passages incertains, pour guider la relecture


class BatchTranscription(BaseModel):
    transcriptions: list[CardTranscription]


class CardGrade(BaseModel):
    """Note d'UNE carte, à partir de la transcription validée par l'élève."""

    numero: int
    feedback: str
    note: str  # "again" | "hard" | "good" | "easy"
    justification: str


class BatchGrade(BaseModel):
    grades: list[CardGrade]


class Suggestion(BaseModel):
    """Classement suggéré d'un poly : année (niveau) et cours (matière)."""

    annee: str  # ex. « MPSI », « L3 », « Master 1 », « Prépa agrég »
    cours: str  # ex. « Probabilités », « Espaces vectoriels normés »
