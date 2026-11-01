"""Module de prétraitement (v0.1 - premier jet)."""

from __future__ import annotations

import numpy as np

from app.validation import DemandeCredit

VARIABLES_MODELE = (
    "age",
    "log_revenu",
    "log_montant",
    "duree_mois",
    "anciennete_activite",
    "taux_effort",
)


class ErreurPretraitement(Exception):
    """Prévue pour les erreurs de transformation."""


def construire_matrice(age, revenu_mensuel, montant_credit, duree_mois, anciennete_activite):
    age, revenu, montant, duree, anciennete = (
        np.asarray(colonne, dtype=float).reshape(-1)
        for colonne in (age, revenu_mensuel, montant_credit, duree_mois, anciennete_activite)
    )
    taux_effort = (montant / duree) / revenu
    return np.column_stack([age, np.log(revenu), np.log(montant), duree, anciennete, taux_effort])


def construire_caracteristiques(demande: DemandeCredit):
    return construire_matrice(
        demande.age,
        demande.revenu_mensuel,
        demande.montant_credit,
        demande.duree_mois,
        demande.anciennete_activite,
    )
