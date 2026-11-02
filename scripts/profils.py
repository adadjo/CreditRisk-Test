"""Profils de demandeurs réalistes pour les mesures de performance (jeu d'évaluation synthétique).

Module volontairement limité à la bibliothèque standard : il est importé aussi bien par le
script de mesure que par le fichier Locust (processus distinct, sans pandas ni scikit-learn).
"""

from __future__ import annotations

import csv
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHAMPS = ("age", "revenu_mensuel", "montant_credit", "duree_mois", "anciennete_activite")
CHAMPS_ENTIERS = ("age", "duree_mois")


def charger_profils(nombre: int = 300) -> list[dict]:
    """Premières demandes du jeu d'évaluation, au format attendu par `POST /predict`."""
    profils: list[dict] = []
    chemin = RACINE / "data" / "jeu_evaluation.csv"
    with chemin.open(encoding="utf-8", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            profil: dict = {champ: float(ligne[champ]) for champ in CHAMPS}
            for champ in CHAMPS_ENTIERS:
                profil[champ] = int(profil[champ])
            profils.append(profil)
            if len(profils) >= nombre:
                break
    return profils


def profil_invalide(profil: dict) -> dict:
    """Variante rejetée par la validation (âge hors limites) : exerce le chemin d'erreur 422."""
    return {**profil, "age": 17}
