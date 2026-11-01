"""Module de validation : format, domaine de valeurs et cohérence des données du demandeur.

Principes appliqués :
- aucune conversion implicite (pas de "250000" -> 250000, pas de True -> 1) ;
- toutes les anomalies sont collectées puis renvoyées ensemble ;
- les messages d'erreur ne reproduisent jamais la valeur reçue (pas d'écho de données hostiles) ;
- un entier JSON peut s'écrire 35 ou 35.0 ; une partie fractionnaire non nulle est rejetée.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app import config

CHAMPS = tuple(config.LIMITES)
LONGUEUR_MAX_NOM_CHAMP = 64


@dataclass(frozen=True)
class DemandeCredit:
    """Demande validée et normalisée (types garantis)."""

    age: int
    revenu_mensuel: float
    montant_credit: float
    duree_mois: int
    anciennete_activite: float


@dataclass(frozen=True)
class DetailErreur:
    """Une anomalie de validation attachée à un champ."""

    champ: str
    code: str
    message: str

    def en_dict(self) -> dict[str, str]:
        return {"champ": self.champ, "code": self.code, "message": self.message}


class ErreurValidation(Exception):
    """Levée quand au moins une anomalie est détectée ; `details` les liste toutes."""

    def __init__(self, details: list[DetailErreur]):
        self.details = details
        super().__init__("; ".join(f"{d.champ}:{d.code}" for d in details))


def _nom_type(valeur: Any) -> str:
    if valeur is None:
        return "valeur nulle"
    if isinstance(valeur, bool):
        return "booléen"
    if isinstance(valeur, str):
        return "texte"
    if isinstance(valeur, list):
        return "liste"
    if isinstance(valeur, dict):
        return "objet"
    return "type inattendu"


def _formater(nombre: float) -> str:
    return f"{int(nombre):,}".replace(",", " ")


def _controler_champ(champ: str, valeur: Any) -> tuple[int | float | None, DetailErreur | None]:
    limite = config.LIMITES[champ]
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        return None, DetailErreur(
            champ, "type_invalide", f"doit être un nombre (reçu : {_nom_type(valeur)})"
        )
    if isinstance(valeur, float) and not math.isfinite(valeur):
        return None, DetailErreur(
            champ, "valeur_non_finie", "doit être un nombre fini (NaN et infinis interdits)"
        )
    if limite.entier and isinstance(valeur, float):
        if not valeur.is_integer():
            return None, DetailErreur(champ, "non_entier", "doit être un nombre entier")
        valeur = int(valeur)
    # Comparaison avant toute conversion : sûre même pour un entier gigantesque.
    if not limite.minimum <= valeur <= limite.maximum:
        intervalle = f"entre {_formater(limite.minimum)} et {_formater(limite.maximum)}"
        return None, DetailErreur(
            champ, "hors_limites", f"doit être compris {intervalle} {limite.unite}".strip()
        )
    return (valeur if limite.entier else float(valeur)), None


def valider_demande(payload: Any) -> DemandeCredit:
    """Valide une demande brute et renvoie une `DemandeCredit` ou lève `ErreurValidation`."""
    if not isinstance(payload, dict):
        raise ErreurValidation(
            [
                DetailErreur(
                    "corps", "schema_invalide", "le corps doit être un objet JSON (clé/valeur)"
                )
            ]
        )

    details: list[DetailErreur] = []
    valeurs: dict[str, int | float] = {}
    for champ in CHAMPS:
        if champ not in payload:
            details.append(DetailErreur(champ, "champ_manquant", "champ obligatoire absent"))
            continue
        valeur, erreur = _controler_champ(champ, payload[champ])
        if erreur is not None:
            details.append(erreur)
        else:
            valeurs[champ] = valeur  # type: ignore[assignment]

    inconnus = sorted(str(cle)[:LONGUEUR_MAX_NOM_CHAMP] for cle in payload if cle not in CHAMPS)
    details.extend(
        DetailErreur(nom, "champ_non_autorise", "champ non autorisé") for nom in inconnus
    )

    if "age" in valeurs and "anciennete_activite" in valeurs:
        plafond = valeurs["age"] - config.AGE_MINIMUM_ACTIVITE
        if valeurs["anciennete_activite"] > plafond:
            details.append(
                DetailErreur(
                    "anciennete_activite",
                    "incoherence",
                    f"ne peut pas dépasser l'âge moins {config.AGE_MINIMUM_ACTIVITE} ans",
                )
            )

    if details:
        raise ErreurValidation(details)
    return DemandeCredit(**valeurs)  # type: ignore[arg-type]


def taux_effort(demande: DemandeCredit) -> float:
    """Mensualité estimée (sans intérêts) rapportée au revenu mensuel."""
    return (demande.montant_credit / demande.duree_mois) / demande.revenu_mensuel


def evaluer_alertes(
    demande: DemandeCredit, domaine: dict[str, dict[str, float]]
) -> list[dict[str, str]]:
    """Signale les entrées valides mais hors du domaine observé à l'entraînement.

    Une entrée invalide est rejetée ; une entrée inhabituelle reste traitée,
    mais accompagnée d'une alerte demandant une analyse supplémentaire.
    """
    valeurs = {champ: getattr(demande, champ) for champ in CHAMPS}
    valeurs["taux_effort"] = taux_effort(demande)
    alertes = []
    for champ, valeur in valeurs.items():
        bornes = domaine.get(champ)
        if bornes is None:
            continue
        if valeur < bornes["min"] or valeur > bornes["max"]:
            alertes.append(
                {
                    "code": "hors_domaine_entrainement",
                    "champ": champ,
                    "message": (
                        f"valeur hors de l'intervalle observé à l'entraînement "
                        f"[{bornes['min']:g} ; {bornes['max']:g}] : prédiction à interpréter "
                        "avec prudence, analyse complémentaire recommandée"
                    ),
                }
            )
    return alertes
