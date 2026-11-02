"""Test de charge progressive de l'API de prédiction (Locust).

Profil : paliers de charge croissants, puis retour à une charge faible pour vérifier que le service
récupère. Chaque utilisateur simulé (un agent de crédit) soumet en moyenne 1 requête par seconde
avec un temps de réflexion exponentiel : les arrivées sont aléatoires (processus de Poisson), donc
« N utilisateurs » ≈ « N req/s demandées ». Une cadence rigoureusement constante synchronise les
utilisateurs et crée des rafales artificielles ; les rafales réelles sont mesurées à part (voir
benchmark_performance.py). 95 % des requêtes sont valides, 5 % sont volontairement invalides
(réponse 422 attendue, comptée comme un succès).

Usage, serveur déjà lancé (le profil ETAPES pilote seul durée et utilisateurs ; -u, -r, -t sont
ignorés) :

    locust -f scripts/locustfile.py --headless --host http://127.0.0.1:8000

Chaque requête est enregistrée dans un journal CSV (variable LOCUST_JOURNAL, par défaut
reports/_tmp/locust_journal.csv) afin de calculer exactement les percentiles par palier.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
import time
from pathlib import Path

from locust import FastHttpUser, LoadTestShape, events, task

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from scripts.profils import charger_profils, profil_invalide  # noqa: E402

DEBIT_PAR_UTILISATEUR = 1.0  # requêtes par seconde et par utilisateur simulé (en moyenne)
PART_REQUETES_INVALIDES = 0.05
TAUX_APPARITION = 100  # utilisateurs créés par seconde lors d'un changement de palier

# (utilisateurs simulés ≈ req/s demandées, durée du palier en secondes)
ETAPES = [
    (5, 30),
    (10, 30),
    (20, 30),
    (50, 25),
    (100, 25),
    (200, 25),
    (300, 25),
    (400, 25),
    (500, 25),
    (600, 25),
    (700, 25),
    (10, 30),  # retour à une charge faible : vérification de la récupération
]

JOURNAL = Path(os.environ.get("LOCUST_JOURNAL", RACINE / "reports" / "_tmp" / "locust_journal.csv"))
PROFIL_JSON = JOURNAL.with_suffix(".profil.json")
PROFILS = charger_profils(300)


class AgentDeCredit(FastHttpUser):
    """Un agent de crédit qui soumet des simulations de risque à des instants aléatoires."""

    network_timeout = 10.0
    connection_timeout = 5.0

    def wait_time(self) -> float:
        return random.expovariate(DEBIT_PAR_UTILISATEUR)

    def on_start(self) -> None:
        self.wait()  # désynchronise les utilisateurs créés au même instant

    @task
    def predire(self) -> None:
        profil = random.choice(PROFILS)
        if random.random() < PART_REQUETES_INVALIDES:
            self._appeler(profil_invalide(profil), "/predict [invalide]", statut_attendu=422)
        else:
            self._appeler(profil, "/predict [valide]", statut_attendu=200)

    def _appeler(self, charge: dict, nom: str, statut_attendu: int) -> None:
        with self.client.post("/predict", json=charge, name=nom, catch_response=True) as reponse:
            if reponse.status_code != statut_attendu:
                reponse.failure(f"statut {reponse.status_code} au lieu de {statut_attendu}")
            elif statut_attendu == 200 and "probabilite_defaut" not in reponse.text:
                reponse.failure("réponse sans probabilité")
            else:
                reponse.success()


class ChargeProgressive(LoadTestShape):
    """Paliers successifs définis par ETAPES ; l'essai s'arrête à la fin du dernier palier."""

    def tick(self):
        ecoule = self.get_run_time()
        fin = 0.0
        for utilisateurs, duree in ETAPES:
            fin += duree
            if ecoule < fin:
                return utilisateurs, TAUX_APPARITION
        return None


class _Journal:
    """Écriture du journal des requêtes (une ligne par requête terminée)."""

    def __init__(self) -> None:
        self.fichier = None
        self.ecrivain = None
        self.debut = 0.0


_journal = _Journal()


@events.test_start.add_listener
def ouvrir_journal(environment, **kwargs):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    _journal.debut = time.time()
    _journal.fichier = JOURNAL.open("w", encoding="utf-8", newline="")
    _journal.ecrivain = csv.writer(_journal.fichier)
    _journal.ecrivain.writerow(["t_s", "nom", "duree_ms", "statut", "succes"])
    PROFIL_JSON.write_text(
        json.dumps(
            {
                "debut_epoch": _journal.debut,
                "etapes": ETAPES,
                "debit_par_utilisateur": DEBIT_PAR_UTILISATEUR,
                "part_requetes_invalides": PART_REQUETES_INVALIDES,
                "taux_apparition": TAUX_APPARITION,
            },
            indent=1,
        ),
        encoding="utf-8",
    )


@events.request.add_listener
def noter_requete(name, response_time, response, exception, start_time=None, **kwargs):
    if _journal.ecrivain is None:
        return
    debut = start_time if start_time is not None else time.time() - response_time / 1000
    statut = getattr(response, "status_code", 0) or 0
    _journal.ecrivain.writerow(
        [
            f"{debut - _journal.debut:.4f}",
            name,
            f"{response_time:.3f}",
            statut,
            int(exception is None),
        ]
    )


@events.test_stop.add_listener
def fermer_journal(environment, **kwargs):
    if _journal.fichier is not None:
        _journal.fichier.close()
        _journal.fichier = None
        _journal.ecrivain = None
