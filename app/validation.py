"""Module de validation (v0.1 - premier jet)."""

from __future__ import annotations

from dataclasses import dataclass

from app import config

CHAMPS = tuple(config.LIMITES)


@dataclass(frozen=True)
class DemandeCredit:
    age: int
    revenu_mensuel: float
    montant_credit: float
    duree_mois: int
    anciennete_activite: float


@dataclass(frozen=True)
class DetailErreur:
    champ: str
    code: str
    message: str

    def en_dict(self):
        return {"champ": self.champ, "code": self.code, "message": self.message}


class ErreurValidation(Exception):
    def __init__(self, details):
        self.details = details
        super().__init__("donnees invalides")


def _lire(payload, champ, erreurs):
    try:
        return float(payload[champ])
    except ValueError:
        erreurs.append(DetailErreur(champ, "type_invalide", "doit être un nombre"))
        return None


def valider_demande(payload):
    erreurs = []
    age = _lire(payload, "age", erreurs)
    revenu = _lire(payload, "revenu_mensuel", erreurs)
    montant = _lire(payload, "montant_credit", erreurs)
    duree = _lire(payload, "duree_mois", erreurs)
    anciennete = _lire(payload, "anciennete_activite", erreurs)

    if age is not None and (age < 18 or age > 75):
        erreurs.append(DetailErreur("age", "hors_limites", "âge hors de l'intervalle [18 ; 75]"))
    if revenu is not None and revenu <= 0:
        erreurs.append(DetailErreur("revenu_mensuel", "hors_limites", "doit être positif"))
    if montant is not None and montant < 0:
        erreurs.append(DetailErreur("montant_credit", "hors_limites", "doit être positif"))
    if duree is not None and (duree < 1 or duree > 120):
        erreurs.append(DetailErreur("duree_mois", "hors_limites", "durée hors de [1 ; 120] mois"))
    if anciennete is not None and anciennete < 0:
        erreurs.append(DetailErreur("anciennete_activite", "hors_limites", "doit être positive"))

    if erreurs:
        raise ErreurValidation(erreurs)
    return DemandeCredit(int(age), revenu, montant, int(duree), anciennete)


def evaluer_alertes(demande, domaine):
    return []  # TODO : signaler les entrées hors du domaine d'entraînement
