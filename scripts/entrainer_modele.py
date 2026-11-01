"""Entraîne le modèle de référence v1.0.0 et fige la base de non-régression.

Produit : model/credit_risk_v1.0.0.{joblib,json}, tests/reference/baseline_v1.0.0.json et
tests/reference/cas_dores.json (probabilités calculées par la chaîne de production).

Usage : python -m scripts.entrainer_modele
"""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from app import config
from app.prediction import ServicePrediction
from app.preprocessing import VARIABLES_MODELE, construire_caracteristiques
from app.validation import valider_demande
from ml.cas_dores import construire_cas_dores
from ml.donnees import CIBLE
from ml.entrainement import entrainer, probabilites_defaut, sauvegarder_modele
from ml.evaluation import metriques

VERSION = "1.0.0"
DATA = config.RACINE / "data"
REFERENCE = config.RACINE / "tests" / "reference"


def _sha256(chemin) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def main() -> None:
    entrainement = pd.read_csv(DATA / "jeu_entrainement.csv")
    evaluation = pd.read_csv(DATA / "jeu_evaluation.csv")

    pipeline = entrainer(entrainement)
    mesures = metriques(evaluation[CIBLE], probabilites_defaut(pipeline, evaluation))
    metadonnees = sauvegarder_modele(
        pipeline,
        entrainement,
        mesures,
        config.RACINE / "model",
        VERSION,
        description="Régression logistique sur données synthétiques (modèle de test versionné).",
    )

    service = ServicePrediction()
    service.charger()
    cas = construire_cas_dores()
    for cas_i in cas:
        demande = valider_demande(cas_i["entree"])
        cas_i["probabilite_reference"] = round(
            service.predire(construire_caracteristiques(demande)), 10
        )
    REFERENCE.mkdir(parents=True, exist_ok=True)
    (REFERENCE / "cas_dores.json").write_text(
        json.dumps(cas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    classifieur = pipeline.named_steps["classifieur"]
    baseline = {
        "version_modele": VERSION,
        "empreinte_modele_sha256": metadonnees["empreinte_sha256"],
        "jeu_evaluation": {
            "fichier": "data/jeu_evaluation.csv",
            "sha256": _sha256(DATA / "jeu_evaluation.csv"),
            "n": int(len(evaluation)),
        },
        "seuil_decision": mesures["seuil"],
        "metriques": mesures,
        "coefficients_standardises": {
            nom: float(valeur)
            for nom, valeur in zip(VARIABLES_MODELE, classifieur.coef_[0], strict=True)
        },
        "ordonnee_origine": float(classifieur.intercept_[0]),
    }
    (REFERENCE / f"baseline_v{VERSION}.json").write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"metriques": mesures, "coefficients": baseline["coefficients_standardises"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
