"""Métriques du modèle et audit des faux négatifs par segments de demandeurs."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app import config
from ml.donnees import CIBLE

# « Défaut prédit » = la couche applicative ne classe pas le dossier en risque faible.
SEUIL_DECISION = config.SEUIL_RISQUE_MODERE

TRANCHES = {
    "age": ("age", [17, 24, 34, 49, 200], ["18-24 ans", "25-34 ans", "35-49 ans", "50 ans et +"]),
    "anciennete": (
        "anciennete_activite",
        [-1, 1, 5, 100],
        ["< 2 ans", "2-5 ans", "> 5 ans"],
    ),
    "duree": ("duree_mois", [0, 18, 120], ["<= 18 mois", ">= 24 mois"]),
    "revenu": (
        "revenu_mensuel",
        [0, 120_000, 250_000, 10**9],
        ["< 120 k FCFA", "120-250 k FCFA", "> 250 k FCFA"],
    ),
}


def metriques(y_vrai, probabilites, seuil: float = SEUIL_DECISION) -> dict[str, float]:
    """Métriques de classification à un seuil donné, plus AUC et Brier (sur probabilités)."""
    y = np.asarray(y_vrai)
    p = np.asarray(probabilites, dtype=float)
    predit = (p >= seuil).astype(int)
    tn = int(((y == 0) & (predit == 0)).sum())
    fp = int(((y == 0) & (predit == 1)).sum())
    fn = int(((y == 1) & (predit == 0)).sum())
    tp = int(((y == 1) & (predit == 1)).sum())
    return {
        "seuil": float(seuil),
        "n": int(len(y)),
        "taux_defaut": float(y.mean()),
        "rappel": float(recall_score(y, predit, zero_division=0)),
        "precision": float(precision_score(y, predit, zero_division=0)),
        "f1": float(f1_score(y, predit, zero_division=0)),
        "exactitude": float(accuracy_score(y, predit)),
        "auc_roc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "taux_faux_negatifs": float(fn / (fn + tp)) if (fn + tp) else 0.0,
        "vp": tp,
        "fp": fp,
        "fn": fn,
        "vn": tn,
    }


def ajouter_tranches(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les colonnes de tranches utilisées par l'audit (âge, ancienneté, durée, revenu)."""
    sortie = df.copy()
    for nom, (colonne, bornes, etiquettes) in TRANCHES.items():
        sortie[f"tranche_{nom}"] = pd.cut(df[colonne], bins=bornes, labels=etiquettes).astype(str)
    return sortie


def _ligne_segment(nom: str, masque: pd.Series, df: pd.DataFrame, p: np.ndarray, seuil: float):
    y = df.loc[masque, CIBLE].to_numpy()
    predit = p[masque.to_numpy()] >= seuil
    defauts = int(y.sum())
    fn = int(((y == 1) & ~predit).sum())
    return {
        "segment": nom,
        "n": int(masque.sum()),
        "defauts": defauts,
        "faux_negatifs": fn,
        "rappel": (defauts - fn) / defauts if defauts else float("nan"),
        "taux_faux_negatifs": fn / defauts if defauts else float("nan"),
    }


def audit_segments(
    df: pd.DataFrame, probabilites, seuil: float = SEUIL_DECISION, croisements: bool = True
) -> pd.DataFrame:
    """Rappel et taux de faux négatifs par tranche, puis par croisement de deux tranches."""
    p = np.asarray(probabilites, dtype=float)
    base = ajouter_tranches(df)
    colonnes = [f"tranche_{nom}" for nom in TRANCHES]
    lignes = [_ligne_segment("Ensemble", pd.Series(True, index=base.index), base, p, seuil)]
    for colonne in colonnes:
        for valeur in sorted(base[colonne].unique()):
            lignes.append(_ligne_segment(valeur, base[colonne] == valeur, base, p, seuil))
    if croisements:
        for c1, c2 in itertools.combinations(colonnes, 2):
            for v1, v2 in itertools.product(sorted(base[c1].unique()), sorted(base[c2].unique())):
                masque = (base[c1] == v1) & (base[c2] == v2)
                if masque.sum():
                    lignes.append(_ligne_segment(f"{v1} & {v2}", masque, base, p, seuil))
    return pd.DataFrame(lignes)
