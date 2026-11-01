"""Génération du jeu de données SYNTHÉTIQUE (voir data/DONNEES.md).

Ces données servent uniquement à tester le système : elles ne démontrent en aucun cas la
performance réelle d'un modèle de crédit. Le mécanisme de génération est volontairement
connu et contient une interaction non linéaire (ancienneté faible x durée longue) que le
modèle linéaire ne peut pas apprendre, afin de pouvoir illustrer l'audit par segments.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COLONNES_ENTREE = [
    "age",
    "revenu_mensuel",
    "montant_credit",
    "duree_mois",
    "anciennete_activite",
]
CIBLE = "defaut"
GRAINE_DONNEES = 2026
DUREES = np.array([6, 9, 12, 18, 24, 36, 48])
PROBA_DUREES = np.array([0.10, 0.10, 0.30, 0.15, 0.20, 0.10, 0.05])

# Paramètres du mécanisme générateur (logit du risque de défaut).
ORDONNEE_ORIGINE = -3.3  # calibrée pour un taux de défaut global proche de 22 %
COEF_TAUX_EFFORT = 4.5
COEF_ANCIENNETE = -0.11
COEF_JEUNE = 0.7
COEF_AGE = -0.01
COEF_DUREE = 0.015
COEF_INTERACTION_CACHEE = 1.9
ECART_TYPE_BRUIT = 0.3


def _sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def generer_donnees(n: int = 12_000, graine: int = GRAINE_DONNEES) -> pd.DataFrame:
    """Jeu synthétique reproductible : 5 variables d'entrée et la cible `defaut` (1 = défaut)."""
    rng = np.random.default_rng(graine)
    age = np.clip(np.rint(rng.normal(38, 10, n)), 18, 70).astype(int)
    revenu = rng.lognormal(np.log(180_000), 0.55, n)
    revenu = np.clip(np.rint(revenu / 1000) * 1000, 40_000, 3_000_000).astype(int)
    duree = rng.choice(DUREES, size=n, p=PROBA_DUREES).astype(int)
    multiple = rng.lognormal(np.log(5.0), 0.6, n)
    montant = np.clip(np.rint(revenu * multiple / 10_000) * 10_000, 50_000, 20_000_000).astype(int)
    anciennete = np.minimum(np.rint(rng.gamma(2.0, 2.5, n)), age - 16).astype(int)

    taux_effort = (montant / duree) / revenu
    logit = (
        ORDONNEE_ORIGINE
        + COEF_TAUX_EFFORT * taux_effort
        + COEF_ANCIENNETE * np.minimum(anciennete, 10)
        + COEF_JEUNE * (age < 25)
        + COEF_AGE * (age - 38)
        + COEF_DUREE * (duree - 12)
        + COEF_INTERACTION_CACHEE * ((anciennete < 2) & (duree >= 24))
        + rng.normal(0, ECART_TYPE_BRUIT, n)
    )
    defaut = (rng.random(n) < _sigmoide(logit)).astype(int)
    return pd.DataFrame(
        {
            "age": age,
            "revenu_mensuel": revenu,
            "montant_credit": montant,
            "duree_mois": duree,
            "anciennete_activite": anciennete,
            CIBLE: defaut,
        }
    )


def separer_entrainement_evaluation(
    df: pd.DataFrame, part_evaluation: float = 0.25, graine: int = GRAINE_DONNEES
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Découpage stratifié et reproductible entre jeu d'entraînement et jeu d'évaluation figé."""
    rng = np.random.default_rng(graine + 1)
    indices_eval = []
    for classe in (0, 1):
        indices = df.index[df[CIBLE] == classe].to_numpy().copy()
        rng.shuffle(indices)
        indices_eval.extend(indices[: int(round(len(indices) * part_evaluation))])
    masque = df.index.isin(indices_eval)
    return df[~masque].reset_index(drop=True), df[masque].reset_index(drop=True)
