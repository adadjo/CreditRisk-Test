"""Module de prédiction (v0.1 - premier jet)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import joblib

from app import config


class ErreurModele(Exception):
    """Classe de base des erreurs liées au modèle."""


class ModeleIndisponible(ErreurModele):
    """Modèle indisponible."""


class ErreurPrediction(ErreurModele):
    code = "erreur_prediction"


class ErreurDimensions(ErreurPrediction):
    code = "incoherence_dimensions"


@dataclass(frozen=True)
class Interpretation:
    niveau: str
    recommandation: str


def calculer_empreinte(chemin: Path) -> str:
    sha = hashlib.sha256()
    with Path(chemin).open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(65536), b""):
            sha.update(bloc)
    return sha.hexdigest()


def interpreter_probabilite(probabilite):
    if probabilite < config.SEUIL_RISQUE_MODERE:
        return Interpretation(
            "faible", "Profil standard : poursuivre l'instruction habituelle du dossier."
        )
    if probabilite <= config.SEUIL_RISQUE_ELEVE:
        return Interpretation(
            "modere",
            "Risque modéré : examen approfondi du dossier et garanties complémentaires à envisager.",
        )
    return Interpretation(
        "eleve",
        "Risque élevé : examen renforcé obligatoire. La décision finale revient à l'agent de crédit.",
    )


class ServicePrediction:
    def __init__(
        self,
        chemin_modele=config.CHEMIN_MODELE,
        chemin_metadonnees=config.CHEMIN_METADONNEES,
    ):
        self.chemin_modele = Path(chemin_modele)
        self.chemin_metadonnees = Path(chemin_metadonnees)
        self._modele = None
        self._metadonnees = None

    @property
    def est_charge(self):
        return self._modele is not None

    @property
    def metadonnees(self):
        return self._metadonnees

    @property
    def domaine_entrainement(self):
        return self._metadonnees["domaine_entrainement"]

    def charger(self):
        self._metadonnees = json.loads(self.chemin_metadonnees.read_text(encoding="utf-8"))
        self._modele = joblib.load(self.chemin_modele)

    def assurer_disponible(self):
        if self._modele is None:
            self.charger()

    def predire(self, caracteristiques):
        self.assurer_disponible()
        return float(self._modele.predict_proba(caracteristiques)[0, 1])
