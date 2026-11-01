"""Entraînement, sauvegarde et rechargement du modèle versionné."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.prediction import calculer_empreinte
from app.preprocessing import VARIABLES_MODELE, construire_matrice
from ml.donnees import CIBLE, COLONNES_ENTREE

GRAINE_MODELE = 42
AVERTISSEMENT_DONNEES = (
    "Données synthétiques générées pour tester le système. Les métriques ne démontrent pas "
    "la performance réelle d'un modèle de crédit."
)


def matrice_depuis_dataframe(df: pd.DataFrame) -> np.ndarray:
    """Même transformation en entraînement et en production (fonction du module de prétraitement)."""
    return construire_matrice(*(df[colonne] for colonne in COLONNES_ENTREE))


def construire_pipeline(
    algorithme: str = "logreg", c: float = 1.0, graine: int = GRAINE_MODELE
) -> Pipeline:
    if algorithme == "logreg":
        classifieur = LogisticRegression(C=c, max_iter=1000, random_state=graine)
    elif algorithme == "hgb":
        classifieur = HistGradientBoostingClassifier(
            max_depth=3, max_iter=150, learning_rate=0.08, random_state=graine
        )
    else:
        raise ValueError(f"algorithme inconnu : {algorithme}")
    return Pipeline([("normalisation", StandardScaler()), ("classifieur", classifieur)])


def entrainer(
    df: pd.DataFrame, algorithme: str = "logreg", c: float = 1.0, graine: int = GRAINE_MODELE
):
    pipeline = construire_pipeline(algorithme, c, graine)
    pipeline.fit(matrice_depuis_dataframe(df), df[CIBLE].to_numpy())
    return pipeline


def probabilites_defaut(pipeline, df: pd.DataFrame) -> np.ndarray:
    classes = list(pipeline.classes_)
    return pipeline.predict_proba(matrice_depuis_dataframe(df))[:, classes.index(1)]


def domaine_entrainement(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Intervalles observés à l'entraînement (variables brutes et taux d'effort)."""
    colonnes = {champ: df[champ] for champ in COLONNES_ENTREE}
    colonnes["taux_effort"] = (df["montant_credit"] / df["duree_mois"]) / df["revenu_mensuel"]
    return {
        nom: {"min": float(serie.min()), "max": float(serie.max())}
        for nom, serie in colonnes.items()
    }


def sauvegarder_modele(
    pipeline,
    df_entrainement: pd.DataFrame,
    metriques_reference: dict,
    dossier: Path,
    version: str,
    nom: str = "credit_risk",
    description: str = "",
) -> dict:
    """Écrit `<nom>_v<version>.joblib` et ses métadonnées JSON (avec empreinte SHA-256)."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin_modele = dossier / f"{nom}_v{version}.joblib"
    joblib.dump(pipeline, chemin_modele)
    algorithme = type(pipeline.named_steps["classifieur"]).__name__
    metadonnees = {
        "nom": nom,
        "version": version,
        "algorithme": algorithme,
        "description": description,
        "date_entrainement": date.today().isoformat(),
        "variables": list(VARIABLES_MODELE),
        "empreinte_sha256": calculer_empreinte(chemin_modele),
        "fichier_modele": chemin_modele.name,
        "domaine_entrainement": domaine_entrainement(df_entrainement),
        "metriques_reference": {
            cle: metriques_reference[cle]
            for cle in ("seuil", "rappel", "precision", "f1", "auc_roc", "exactitude", "brier")
        },
        "donnees": {
            "type": "synthetique",
            "avertissement": AVERTISSEMENT_DONNEES,
            "n_entrainement": int(len(df_entrainement)),
            "taux_defaut_entrainement": float(df_entrainement[CIBLE].mean()),
        },
        "bibliotheques": {"scikit_learn": sklearn.__version__, "numpy": np.__version__},
    }
    chemin_meta = dossier / f"{nom}_v{version}.json"
    chemin_meta.write_text(
        json.dumps(metadonnees, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadonnees
