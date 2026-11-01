"""Module de prétraitement : transforme une demande validée en variables du modèle.

La même fonction vectorisée sert à l'entraînement et à l'inférence, ce qui garantit
l'absence de décalage entre les deux (training/serving skew).
"""

from __future__ import annotations

import numpy as np

from app.validation import DemandeCredit

# Ordre exact des colonnes attendues par le modèle.
VARIABLES_MODELE = (
    "age",
    "log_revenu",
    "log_montant",
    "duree_mois",
    "anciennete_activite",
    "taux_effort",
)


class ErreurPretraitement(Exception):
    """Le prétraitement ne peut pas produire un vecteur exploitable."""


def construire_matrice(
    age, revenu_mensuel, montant_credit, duree_mois, anciennete_activite
) -> np.ndarray:
    """Construit la matrice (n, 6) des variables du modèle à partir de colonnes brutes."""
    try:
        age, revenu, montant, duree, anciennete = (
            np.asarray(colonne, dtype=float).reshape(-1)
            for colonne in (age, revenu_mensuel, montant_credit, duree_mois, anciennete_activite)
        )
        with np.errstate(all="raise"):
            taux_effort = (montant / duree) / revenu
            matrice = np.column_stack(
                [age, np.log(revenu), np.log(montant), duree, anciennete, taux_effort]
            )
    except (FloatingPointError, ValueError, TypeError, OverflowError) as exc:
        raise ErreurPretraitement("transformation impossible") from exc
    if not np.all(np.isfinite(matrice)):
        raise ErreurPretraitement("variables non finies après transformation")
    return matrice


def construire_caracteristiques(demande: DemandeCredit) -> np.ndarray:
    """Vecteur (1, 6) prêt pour le modèle, pour une demande validée."""
    try:
        return construire_matrice(
            demande.age,
            demande.revenu_mensuel,
            demande.montant_credit,
            demande.duree_mois,
            demande.anciennete_activite,
        )
    except AttributeError as exc:
        raise ErreurPretraitement("variable attendue absente") from exc
