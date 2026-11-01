"""Paramètres centralisés du prototype : limites métier, seuils d'interprétation, chemins."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

VERSION_APPLICATION = "0.1.0"

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_MODELE = RACINE / "model" / "credit_risk_v1.0.0.joblib"
CHEMIN_METADONNEES = RACINE / "model" / "credit_risk_v1.0.0.json"


@dataclass(frozen=True)
class Limite:
    """Domaine de validité d'une variable d'entrée (bornes incluses)."""

    minimum: float
    maximum: float
    entier: bool = False
    unite: str = ""


# Ordre canonique des champs de la demande.
LIMITES: dict[str, Limite] = {
    "age": Limite(18, 75, entier=True, unite="ans"),
    "revenu_mensuel": Limite(1, 20_000_000, unite="FCFA"),
    "montant_credit": Limite(1, 200_000_000, unite="FCFA"),
    "duree_mois": Limite(1, 120, entier=True, unite="mois"),
    "anciennete_activite": Limite(0, 60, unite="ans"),
}

# Cohérence : on ne peut pas exercer une activité avant cet âge.
AGE_MINIMUM_ACTIVITE = 16

# Interprétation de la probabilité de défaut (couche applicative).
SEUIL_RISQUE_MODERE = 0.30  # p < 0.30 : faible ; 0.30 <= p < 0.60 : modéré
SEUIL_RISQUE_ELEVE = 0.60  # p >= 0.60 : élevé

# Un corps de requête valide pèse environ 150 octets.
TAILLE_MAX_CORPS = 10_000
