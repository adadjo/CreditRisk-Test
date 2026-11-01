"""Module de prédiction : chargement contrôlé du modèle, inférence, interprétation du résultat."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from app import config
from app.preprocessing import VARIABLES_MODELE

journal = logging.getLogger("credit_risk.prediction")

CLES_METADONNEES_OBLIGATOIRES = (
    "nom",
    "version",
    "algorithme",
    "variables",
    "empreinte_sha256",
    "domaine_entrainement",
)


class ErreurModele(Exception):
    """Classe de base des erreurs liées au modèle."""


class ModeleIndisponible(ErreurModele):
    """Le modèle n'a pas pu être chargé ou n'a pas passé les contrôles d'intégrité."""


class ErreurPrediction(ErreurModele):
    """Échec de l'inférence ou résultat non conforme au contrat."""

    code = "erreur_prediction"


class ErreurDimensions(ErreurPrediction):
    """Le vecteur d'entrée ne correspond pas aux dimensions attendues par le modèle."""

    code = "incoherence_dimensions"


@dataclass(frozen=True)
class Interpretation:
    niveau: str
    recommandation: str


def calculer_empreinte(chemin: Path) -> str:
    """Empreinte SHA-256 d'un fichier (lecture par blocs)."""
    sha = hashlib.sha256()
    with Path(chemin).open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(65536), b""):
            sha.update(bloc)
    return sha.hexdigest()


def interpreter_probabilite(probabilite: float) -> Interpretation:
    """Traduit une probabilité de défaut en niveau de risque exploitable par un agent de crédit.

    p < 0.30 : faible ; 0.30 <= p < 0.60 : modéré ; p >= 0.60 : élevé.
    """
    if (
        isinstance(probabilite, bool)
        or not isinstance(probabilite, int | float)
        or not math.isfinite(probabilite)
        or not 0.0 <= probabilite <= 1.0
    ):
        raise ValueError("probabilité hors contrat")
    if probabilite < config.SEUIL_RISQUE_MODERE:
        return Interpretation(
            "faible", "Profil standard : poursuivre l'instruction habituelle du dossier."
        )
    if probabilite < config.SEUIL_RISQUE_ELEVE:
        return Interpretation(
            "modere",
            "Risque modéré : examen approfondi du dossier et garanties complémentaires à envisager.",
        )
    return Interpretation(
        "eleve",
        "Risque élevé : examen renforcé obligatoire. La décision finale revient à l'agent de crédit.",
    )


class ServicePrediction:
    """Charge le modèle versionné, contrôle son intégrité puis produit des probabilités."""

    def __init__(
        self,
        chemin_modele: Path | str = config.CHEMIN_MODELE,
        chemin_metadonnees: Path | str = config.CHEMIN_METADONNEES,
    ):
        self.chemin_modele = Path(chemin_modele)
        self.chemin_metadonnees = Path(chemin_metadonnees)
        self._modele = None
        self._metadonnees: dict | None = None
        self._indice_defaut = 1
        self._verrou = threading.Lock()

    @property
    def est_charge(self) -> bool:
        return self._modele is not None

    @property
    def metadonnees(self) -> dict:
        if self._metadonnees is None:
            raise ModeleIndisponible("métadonnées non chargées")
        return copy.deepcopy(self._metadonnees)

    @property
    def domaine_entrainement(self) -> dict[str, dict[str, float]]:
        if self._metadonnees is None:
            raise ModeleIndisponible("métadonnées non chargées")
        return self._metadonnees["domaine_entrainement"]

    def _lire_metadonnees(self) -> dict:
        if not self.chemin_metadonnees.is_file():
            raise ModeleIndisponible("fichier de métadonnées introuvable")
        try:
            metadonnees = json.loads(self.chemin_metadonnees.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModeleIndisponible("métadonnées illisibles") from exc
        if not isinstance(metadonnees, dict) or any(
            cle not in metadonnees for cle in CLES_METADONNEES_OBLIGATOIRES
        ):
            raise ModeleIndisponible("métadonnées incomplètes")
        if list(metadonnees["variables"]) != list(VARIABLES_MODELE):
            raise ModeleIndisponible("variables des métadonnées incohérentes avec le prétraitement")
        return metadonnees

    def charger(self) -> None:
        """Charge le modèle ; lève `ModeleIndisponible` si un contrôle échoue."""
        with self._verrou:
            self._modele = None
            self._metadonnees = None
            try:
                metadonnees = self._lire_metadonnees()
                if not self.chemin_modele.is_file():
                    raise ModeleIndisponible("fichier modèle introuvable")
                if calculer_empreinte(self.chemin_modele) != metadonnees["empreinte_sha256"]:
                    raise ModeleIndisponible("empreinte SHA-256 du modèle non conforme")
                modele = joblib.load(self.chemin_modele)
                if not (
                    hasattr(modele, "predict_proba")
                    and hasattr(modele, "classes_")
                    and getattr(modele, "n_features_in_", None) == len(VARIABLES_MODELE)
                    and 1 in list(modele.classes_)
                ):
                    raise ModeleIndisponible("objet modèle non conforme au contrat")
            except ModeleIndisponible:
                journal.error("Chargement du modèle refusé", exc_info=True)
                raise
            except Exception as exc:
                journal.error("Chargement du modèle impossible", exc_info=True)
                raise ModeleIndisponible("chargement impossible") from exc
            self._modele = modele
            self._metadonnees = metadonnees
            self._indice_defaut = list(modele.classes_).index(1)

    def assurer_disponible(self) -> None:
        """Tente un chargement si le modèle n'est pas encore en mémoire."""
        if self._modele is None:
            self.charger()

    def predire(self, caracteristiques: np.ndarray) -> float:
        """Probabilité de défaut pour un vecteur (1, n) ; toujours finie et dans [0, 1]."""
        self.assurer_disponible()
        modele = self._modele
        try:
            x = np.asarray(caracteristiques, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ErreurPrediction("entrée non numérique") from exc
        attendu = modele.n_features_in_
        if x.ndim != 2 or x.shape[0] != 1 or x.shape[1] != attendu:
            raise ErreurDimensions(f"forme {x.shape} incompatible avec {attendu} variables")
        if not np.all(np.isfinite(x)):
            raise ErreurPrediction("variables non finies")
        try:
            probabilite = float(modele.predict_proba(x)[0, self._indice_defaut])
        except Exception as exc:
            raise ErreurPrediction("échec de l'inférence") from exc
        if not math.isfinite(probabilite) or not 0.0 <= probabilite <= 1.0:
            raise ErreurPrediction("probabilité hors contrat")
        return probabilite
