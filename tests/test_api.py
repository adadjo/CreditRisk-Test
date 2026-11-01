"""Tests fonctionnels de l'API : /health, /predict et /model-info face à leur contrat."""

from __future__ import annotations

import math
import shutil

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app, create_app
from app.prediction import ServicePrediction, interpreter_probabilite
from tests.scenarios import PAYLOAD_VALIDE, SCENARIOS_API, avec, executer_scenario

CLES_REPONSE_PREDICT = {
    "probabilite_defaut",
    "niveau_risque",
    "recommandation",
    "alertes",
    "version_modele",
    "id_requete",
}
CLES_ERREUR = {"erreur", "message", "id_requete"}


# --- Exemple de l'énoncé, adapté au contrat documenté (champ probabilite_defaut) ---------
@pytest.mark.exigence("EX04")
def test_requete_valide():
    client = TestClient(app)
    response = client.post(
        "/predict",
        json={
            "age": 35,
            "revenu_mensuel": 250000,
            "montant_credit": 1000000,
            "duree_mois": 12,
            "anciennete_activite": 4,
        },
    )
    assert response.status_code == 200
    resultat = response.json()
    assert 0 <= resultat["probabilite_defaut"] <= 1


# --- Les 26 scénarios documentés (tableau des résultats) ---------------------------------
@pytest.mark.parametrize(
    "scenario",
    [pytest.param(s, id=s.id, marks=pytest.mark.exigence(*s.exigences)) for s in SCENARIOS_API],
)
def test_scenarios_api(scenario, clients):
    observe = executer_scenario(scenario, clients)
    assert observe["statut_observe"] == scenario.statut_attendu, observe["texte"][:300]
    assert observe["erreur_observee"] == scenario.code_erreur, observe["texte"][:300]
    for detail in scenario.details:
        assert detail in observe["details_observes"]
    corps = observe["corps"]
    assert observe["en_tetes"]["x-request-id"] == corps["id_requete"]
    if scenario.statut_attendu == 200:
        assert set(corps) == CLES_REPONSE_PREDICT
        assert math.isfinite(corps["probabilite_defaut"]) and 0 <= corps["probabilite_defaut"] <= 1
    else:
        assert set(corps) >= CLES_ERREUR
        assert "Traceback" not in observe["texte"] and 'File "' not in observe["texte"]
    if scenario.id == "S11":
        assert observe["en_tetes"]["retry-after"] == "30"
    if scenario.id == "S23":
        assert "POST" in observe["en_tetes"]["allow"]


def test_scenarios_couvrent_les_cas_obligatoires_de_l_enonce():
    """Garde-fou : les dix scénarios imposés par l'énoncé figurent bien dans le catalogue."""
    ids = {s.id for s in SCENARIOS_API}
    assert {f"S{n:02d}" for n in range(1, 13)} <= ids and len(SCENARIOS_API) >= 25


# --- Contrat de /predict ----------------------------------------------------------------
@pytest.mark.exigence("EX04", "EX16")
def test_contrat_de_reponse_predict(client):
    corps = client.post("/predict", json=PAYLOAD_VALIDE).json()
    assert set(corps) == CLES_REPONSE_PREDICT
    assert isinstance(corps["probabilite_defaut"], float)
    assert corps["niveau_risque"] == interpreter_probabilite(corps["probabilite_defaut"]).niveau
    assert corps["alertes"] == [] and corps["version_modele"] == "1.0.0"


@pytest.mark.exigence("EX04")
@pytest.mark.parametrize(
    "modifs",
    [
        {},
        {"age": 18, "anciennete_activite": 0},
        {"age": 75, "anciennete_activite": 30},
        {"duree_mois": 1},
        {"duree_mois": 120},
        {"revenu_mensuel": 1},
        {"montant_credit": 200_000_000},
        {"revenu_mensuel": 20_000_000, "montant_credit": 1},
    ],
    ids=[
        "nominal",
        "age_min",
        "age_max",
        "duree_min",
        "duree_max",
        "revenu_min",
        "montant_max",
        "extremes",
    ],
)
def test_probabilite_valide_sur_demandes_variees(client, modifs):
    reponse = client.post("/predict", json=avec(**modifs))
    assert reponse.status_code == 200
    p = reponse.json()["probabilite_defaut"]
    assert math.isfinite(p) and 0.0 <= p <= 1.0


@pytest.mark.exigence("EX10", "EX11")
def test_identifiant_de_requete_unique(client):
    ids = {client.post("/predict", json=PAYLOAD_VALIDE).headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5 and all(len(i) == 16 for i in ids)


@pytest.mark.exigence("EX06", "EX05")
def test_validation_prioritaire_sur_la_disponibilite_du_modele(client_sans_modele):
    """Une demande invalide reçoit 422 même si le modèle est absent (le client corrige d'abord)."""
    assert client_sans_modele.post("/predict", json=avec(age=-1)).status_code == 422
    assert client_sans_modele.post("/predict", json=PAYLOAD_VALIDE).status_code == 503


# --- /health ----------------------------------------------------------------------------
@pytest.mark.exigence("EX05")
def test_health_service_disponible(client):
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json() == {
        "statut": "ok",
        "modele_charge": True,
        "version_application": config.VERSION_APPLICATION,
    }


@pytest.mark.exigence("EX05")
def test_health_signale_l_indisponibilite_du_modele(client_sans_modele):
    reponse = client_sans_modele.get("/health")
    assert reponse.status_code == 503
    assert reponse.json()["statut"] == "indisponible" and reponse.json()["modele_charge"] is False


@pytest.mark.exigence("EX05")
def test_indisponibilite_coherente_sur_les_trois_endpoints(client_sans_modele):
    assert client_sans_modele.get("/health").status_code == 503
    assert client_sans_modele.get("/model-info").status_code == 503
    assert client_sans_modele.post("/predict", json=PAYLOAD_VALIDE).status_code == 503


@pytest.mark.exigence("EX05")
def test_reprise_automatique_apres_indisponibilite(tmp_path):
    """Le modèle apparaît après le démarrage : le service se rétablit sans redémarrage."""
    dossier = tmp_path / "modele"
    dossier.mkdir()
    service = ServicePrediction(dossier / "m.joblib", dossier / "m.json")
    client = TestClient(create_app(service))
    assert client.get("/health").status_code == 503
    shutil.copy(config.CHEMIN_MODELE, dossier / "m.joblib")
    shutil.copy(config.CHEMIN_METADONNEES, dossier / "m.json")
    assert client.get("/health").status_code == 200
    assert client.post("/predict", json=PAYLOAD_VALIDE).status_code == 200


# --- /model-info ------------------------------------------------------------------------
@pytest.mark.exigence("EX14")
def test_model_info_contrat(client):
    reponse = client.get("/model-info")
    assert reponse.status_code == 200
    info = reponse.json()
    assert {
        "nom",
        "version",
        "algorithme",
        "variables",
        "nb_variables",
        "empreinte_sha256",
        "metriques_reference",
        "donnees",
        "seuils_risque",
        "version_application",
    } <= set(info)
    assert info["nb_variables"] == len(info["variables"]) == 6
    assert info["donnees"]["type"] == "synthetique"
    assert info["seuils_risque"] == {"modere": 0.3, "eleve": 0.6}


@pytest.mark.exigence("EX11", "EX14")
def test_model_info_n_expose_ni_chemin_ni_version_de_bibliotheque(client):
    texte = client.get("/model-info").text
    assert "/home" not in texte and ".joblib" not in texte and "scikit" not in texte.lower()


# --- Contrat documenté (OpenAPI) --------------------------------------------------------
@pytest.mark.exigence("EX09", "EX10")
def test_contrat_openapi_documente_endpoints_et_schema(client):
    spec = client.get("/openapi.json").json()
    assert {"/health", "/predict", "/model-info"} <= set(spec["paths"])
    schema = spec["paths"]["/predict"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert schema["additionalProperties"] is False
    assert list(schema["properties"]) == list(config.LIMITES) == schema["required"]
    assert {"200", "400", "413", "415", "422", "500", "503"} <= set(
        spec["paths"]["/predict"]["post"]["responses"]
    )
