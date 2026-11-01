"""Fixtures communes et rapport JSON des résultats (alimente la matrice de traçabilité)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.prediction import ServicePrediction
from tests.exigences import EXIGENCES_PAR_ID
from tests.scenarios import PAYLOAD_VALIDE

RACINE = Path(__file__).resolve().parent.parent
RESULTATS: list[dict] = []


def pytest_addoption(parser):
    parser.addoption(
        "--resultats-json",
        default=None,
        help="écrit les résultats détaillés (avec exigences) dans ce fichier JSON",
    )


def pytest_collection_modifyitems(items):
    """Refuse un marqueur `exigence` qui référence un identifiant inconnu du catalogue."""
    for item in items:
        for marqueur in item.iter_markers("exigence"):
            for identifiant in marqueur.args:
                if identifiant not in EXIGENCES_PAR_ID:
                    raise pytest.UsageError(f"{item.nodeid} : exigence inconnue {identifiant}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultat = yield
    rapport = resultat.get_result()
    if rapport.when == "call" or (rapport.when == "setup" and rapport.outcome != "passed"):
        exigences = sorted({i for m in item.iter_markers("exigence") for i in m.args})
        RESULTATS.append(
            {
                "test": item.nodeid,
                "fonction": item.originalname or item.name,
                "exigences": exigences,
                "resultat": rapport.outcome,
                "duree_s": round(rapport.duration, 4),
            }
        )


def pytest_sessionfinish(session, exitstatus):
    chemin = session.config.getoption("--resultats-json")
    if chemin:
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        Path(chemin).write_text(
            json.dumps(
                {"statut_sortie": int(exitstatus), "tests": RESULTATS}, indent=1, ensure_ascii=False
            ),
            encoding="utf-8",
        )


@pytest.fixture(scope="session")
def service() -> ServicePrediction:
    """Service de prédiction réel (modèle versionné du dépôt)."""
    instance = ServicePrediction()
    instance.charger()
    return instance


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def client_sans_modele(tmp_path_factory) -> TestClient:
    absent = tmp_path_factory.mktemp("absent") / "inexistant.joblib"
    return TestClient(create_app(ServicePrediction(absent, absent.with_suffix(".json"))))


@pytest.fixture(scope="session")
def clients(client, client_sans_modele) -> dict:
    return {"normal": client, "sans_modele": client_sans_modele}


@pytest.fixture
def payload() -> dict:
    return dict(PAYLOAD_VALIDE)


@pytest.fixture
def fabrique_client():
    """Construit un client avec un service donné ; erreurs serveur non relancées (réponse 500 testée)."""

    def _construire(service_injecte: ServicePrediction) -> TestClient:
        return TestClient(create_app(service_injecte), raise_server_exceptions=False)

    return _construire


@pytest.fixture
def journal_serveur(caplog):
    caplog.set_level(logging.INFO, logger="credit_risk")
    return caplog
