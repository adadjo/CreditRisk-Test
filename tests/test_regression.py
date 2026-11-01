"""Tests de non-régression du logiciel et du modèle (référence : modèle v1.0.0, jeu d'évaluation figé)."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.prediction import ServicePrediction, calculer_empreinte, interpreter_probabilite
from ml.comparaison import charger_tolerances, comparer
from ml.donnees import CIBLE
from ml.entrainement import entrainer, probabilites_defaut
from ml.evaluation import metriques
from tests.scenarios import SCENARIOS_API, executer_scenario

REFERENCE = config.RACINE / "tests" / "reference"
DATA = config.RACINE / "data"
BASELINE = json.loads((REFERENCE / "baseline_v1.0.0.json").read_text(encoding="utf-8"))
CAS_DORES = json.loads((REFERENCE / "cas_dores.json").read_text(encoding="utf-8"))
CONTRAT = json.loads((REFERENCE / "contrat_api.json").read_text(encoding="utf-8"))
TOLERANCES = charger_tolerances()
EVALUATION = pd.read_csv(DATA / "jeu_evaluation.csv")
ENTRAINEMENT = pd.read_csv(DATA / "jeu_entrainement.csv")


@pytest.fixture(scope="module")
def modele_reference():
    return joblib.load(config.CHEMIN_MODELE)


@pytest.fixture(scope="module")
def mesures_actuelles(modele_reference):
    return metriques(EVALUATION[CIBLE], probabilites_defaut(modele_reference, EVALUATION))


def dores_avec(probabilites: list[float]) -> tuple[list[dict], list[float]]:
    return CAS_DORES, probabilites


# --- Référence figée --------------------------------------------------------------------
@pytest.mark.exigence("EX07", "EX14")
def test_jeu_d_evaluation_et_modele_de_reference_figes():
    empreinte = hashlib.sha256((DATA / "jeu_evaluation.csv").read_bytes()).hexdigest()
    assert empreinte == BASELINE["jeu_evaluation"]["sha256"]
    assert len(EVALUATION) == BASELINE["jeu_evaluation"]["n"]
    assert calculer_empreinte(config.CHEMIN_MODELE) == BASELINE["empreinte_modele_sha256"]
    assert config.CHEMIN_MODELE.name == f"credit_risk_v{BASELINE['version_modele']}.joblib"


@pytest.mark.exigence("EX07")
def test_tolerances_definies_avant_la_comparaison_et_completes():
    assert TOLERANCES["definies_le"] <= "2026-11-10"
    assert {"rappel", "f1", "auc_roc", "precision", "brier"} <= set(TOLERANCES["metriques"])
    assert (
        TOLERANCES["metriques"]["rappel"]["critique"] and TOLERANCES["metriques"]["f1"]["critique"]
    )
    assert BASELINE["metriques"]["rappel"] >= TOLERANCES["metriques"]["rappel"]["plancher_absolu"]


# --- Métriques du modèle courant contre la référence -------------------------------------
@pytest.mark.exigence("EX07")
def test_metriques_du_modele_courant_conformes_a_la_reference(mesures_actuelles):
    resultat = comparer(BASELINE["metriques"], mesures_actuelles, TOLERANCES)
    assert resultat["verdict"] == "CONFORME", resultat["controles_metriques"]
    for cle in ("rappel", "f1", "precision", "auc_roc", "brier"):
        assert mesures_actuelles[cle] == pytest.approx(BASELINE["metriques"][cle], abs=1e-12)


@pytest.mark.exigence("EX07")
@pytest.mark.parametrize(
    ("modifs", "verdict", "metrique_en_cause"),
    [
        ({}, "CONFORME", None),
        ({"rappel": -0.029}, "CONFORME", None),
        ({"rappel": -0.03}, "CONFORME", None),
        ({"rappel": -0.031}, "REGRESSION", "rappel"),
        ({"f1": -0.031}, "REGRESSION", "f1"),
        ({"f1": -0.029, "rappel": +0.02}, "CONFORME", None),
        ({"auc_roc": -0.019}, "CONFORME", None),
        ({"auc_roc": -0.021}, "REVUE_REQUISE", "auc_roc"),
        ({"precision": -0.051}, "REVUE_REQUISE", "precision"),
        ({"brier": +0.011}, "REVUE_REQUISE", "brier"),
    ],
    ids=[
        "identique",
        "rappel_-0.029",
        "rappel_-0.03_limite",
        "rappel_-0.031",
        "f1_-0.031",
        "rappel_en_hausse_compense",
        "auc_-0.019",
        "auc_-0.021",
        "precision_-0.051",
        "brier_+0.011",
    ],
)
def test_regles_de_tolerance_aux_bornes(modifs, verdict, metrique_en_cause):
    candidat = deepcopy(BASELINE["metriques"])
    for cle, delta in modifs.items():
        candidat[cle] += delta
    resultat = comparer(BASELINE["metriques"], candidat, TOLERANCES)
    assert resultat["verdict"] == verdict
    if metrique_en_cause:
        statuts = {c["metrique"]: c["statut"] for c in resultat["controles_metriques"]}
        assert statuts[metrique_en_cause] in ("ECHEC", "ECART")


@pytest.mark.exigence("EX07")
def test_plancher_absolu_protege_contre_la_derive_cumulative():
    """Chaque version perd moins de 0,03 de rappel, mais la somme finit sous le plancher : bloqué."""
    reference = {**BASELINE["metriques"], "rappel": 0.57}
    candidat = {**reference, "rappel": 0.545}
    resultat = comparer(reference, candidat, TOLERANCES)
    rappel = next(c for c in resultat["controles_metriques"] if c["metrique"] == "rappel")
    assert rappel["statut"] == "ECHEC" and "plancher" in rappel["detail"]
    assert resultat["verdict"] == "REGRESSION"


# --- Candidats réels : le contrôle de non-régression s'exécute --------------------------
def evaluer_candidat(**options):
    pipeline = entrainer(ENTRAINEMENT, **options)
    mesures = metriques(EVALUATION[CIBLE], probabilites_defaut(pipeline, EVALUATION))
    dores = probabilites_defaut(pipeline, pd.DataFrame([c["entree"] for c in CAS_DORES]))
    return comparer(BASELINE["metriques"], mesures, TOLERANCES, CAS_DORES, list(dores))


@pytest.mark.exigence("EX07")
def test_candidat_equivalent_est_conforme():
    resultat = evaluer_candidat(c=0.5)
    assert resultat["verdict"] == "CONFORME"
    assert (
        resultat["cas_dores"]["ecart_absolu_max"]
        <= TOLERANCES["cas_dores"]["ecart_probabilite_max"]
    )


@pytest.mark.exigence("EX07")
def test_candidat_sur_regularise_est_detecte_comme_regression():
    """Une régularisation excessive écrase les probabilités : le rappel s'effondre, la livraison est bloquée."""
    resultat = evaluer_candidat(c=0.0005)
    statuts = {c["metrique"]: c["statut"] for c in resultat["controles_metriques"]}
    assert resultat["verdict"] == "REGRESSION"
    assert statuts["rappel"] == "ECHEC"


@pytest.mark.exigence("EX07")
def test_candidat_ameliore_n_est_pas_une_regression():
    """Un modèle non linéaire ne dégrade aucun critère ; les dérives de probabilité imposent une revue."""
    resultat = evaluer_candidat(algorithme="hgb")
    assert resultat["verdict"] in ("CONFORME", "REVUE_REQUISE")
    assert all(c["statut"] == "OK" for c in resultat["controles_metriques"] if c["critique"])


# --- Cas dorés et cohérence des sorties -------------------------------------------------
@pytest.mark.exigence("EX07", "EX13")
def test_cas_dores_identiques_a_la_reference(service):
    from app.preprocessing import construire_caracteristiques
    from app.validation import valider_demande

    for cas in CAS_DORES:
        p = service.predire(construire_caracteristiques(valider_demande(cas["entree"])))
        assert abs(p - cas["probabilite_reference"]) <= 1e-9, cas["id"]
        assert (
            interpreter_probabilite(p).niveau
            == interpreter_probabilite(cas["probabilite_reference"]).niveau
        )


@pytest.mark.exigence("EX07", "EX04", "EX16")
@pytest.mark.parametrize("cas", CAS_DORES, ids=[c["id"] for c in CAS_DORES])
def test_cas_dores_via_l_api(client, cas):
    reponse = client.post("/predict", json=cas["entree"])
    assert reponse.status_code == 200
    corps = reponse.json()
    assert abs(corps["probabilite_defaut"] - cas["probabilite_reference"]) <= 1e-6
    assert corps["niveau_risque"] == interpreter_probabilite(cas["probabilite_reference"]).niveau


@pytest.mark.exigence("EX07")
def test_contrat_des_sorties_inchange(client):
    def types(corps):
        return {cle: type(valeur).__name__ for cle, valeur in corps.items()}

    assert (
        types(client.post("/predict", json=CAS_DORES[0]["entree"]).json()) == CONTRAT["predict_200"]
    )
    assert types(client.get("/health").json()) == CONTRAT["health_200"]
    assert types(client.get("/model-info").json()) == CONTRAT["model_info_200"]
    erreur = client.post("/predict", json={"age": -1}).json()
    assert types(erreur) == CONTRAT["predict_erreur"]
    niveaux = {client.post("/predict", json=c["entree"]).json()["niveau_risque"] for c in CAS_DORES}
    assert niveaux == set(CONTRAT["niveaux_risque"])


@pytest.mark.exigence("EX07")
def test_comportement_fonctionnel_identique_sur_une_instance_neuve(clients, service):
    """Rejouer les 27 scénarios sur une application recréée donne exactement les mêmes résultats."""
    neuve = {
        "normal": TestClient(create_app(ServicePrediction())),
        "sans_modele": clients["sans_modele"],
    }
    for scenario in SCENARIOS_API:
        a, b = executer_scenario(scenario, clients), executer_scenario(scenario, neuve)
        assert (a["statut_observe"], a["erreur_observee"], a["details_observes"]) == (
            b["statut_observe"],
            b["erreur_observee"],
            b["details_observes"],
        ), scenario.id


# --- Sauvegarde, rechargement, réentraînement -------------------------------------------
@pytest.mark.exigence("EX13", "EX14")
def test_predictions_identiques_apres_sauvegarde_et_rechargement(modele_reference, tmp_path):
    chemin = tmp_path / "copie.joblib"
    joblib.dump(modele_reference, chemin)
    recharge = joblib.load(chemin)
    avant = probabilites_defaut(modele_reference, EVALUATION)
    apres = probabilites_defaut(recharge, EVALUATION)
    assert np.max(np.abs(avant - apres)) <= TOLERANCES["rechargement"]["ecart_max_absolu"]


@pytest.mark.exigence("EX13", "EX07")
def test_reentrainement_reproductible_et_conforme_a_la_reference(modele_reference):
    premier, second = entrainer(ENTRAINEMENT), entrainer(ENTRAINEMENT)
    p1, p2 = probabilites_defaut(premier, EVALUATION), probabilites_defaut(second, EVALUATION)
    assert np.max(np.abs(p1 - p2)) <= TOLERANCES["reproductibilite"]["ecart_max_absolu"]
    coefficients = premier.named_steps["classifieur"].coef_[0]
    attendus = list(BASELINE["coefficients_standardises"].values())
    assert np.allclose(coefficients, attendus, atol=1e-8), (
        "le réentraînement ne reproduit plus la référence"
    )
    p_ref = probabilites_defaut(modele_reference, EVALUATION)
    assert np.max(np.abs(p1 - p_ref)) <= 1e-8


@pytest.mark.exigence("EX13")
def test_graine_differente_reste_dans_la_tolerance():
    """Régression logistique (lbfgs) : la graine n'influence pas la solution, donc aucune dérive."""
    a = probabilites_defaut(entrainer(ENTRAINEMENT, graine=1), EVALUATION)
    b = probabilites_defaut(entrainer(ENTRAINEMENT, graine=2), EVALUATION)
    assert np.max(np.abs(a - b)) <= TOLERANCES["reproductibilite"]["ecart_max_absolu"]
