"""Traçabilité des exigences et conformité du dépôt (arborescence, CI, dépendances, documentation)."""

from __future__ import annotations

import re

import pytest
import yaml

from app import config
from tests.exigences import EXIGENCES, EXIGENCES_PAR_ID
from tests.plan_de_test import PLAN

RACINE = config.RACINE
FICHIERS_DE_LA_SUITE = {
    "test_validation.py",
    "test_api.py",
    "test_integration.py",
    "test_robustness.py",
    "test_regression.py",
    "test_performance.py",
    "test_demo_echec.py",
    "test_donnees_modele.py",
}


def suite_complete(items) -> bool:
    return {item.path.name for item in items} >= FICHIERS_DE_LA_SUITE


# --- Matrice de traçabilité -------------------------------------------------------------
def test_sept_exigences_imposees_et_au_moins_cinq_ajoutees():
    identifiants = [e.id for e in EXIGENCES]
    assert identifiants[:7] == [f"EX0{n}" for n in range(1, 8)]
    assert all(e.origine == "Énoncé" for e in EXIGENCES[:7])
    assert sum(e.origine == "Ajoutée" for e in EXIGENCES) >= 5


def test_priorites_calculees_a_partir_de_la_gravite_et_de_la_probabilite():
    assert EXIGENCES_PAR_ID["EX02"].score == 9 and EXIGENCES_PAR_ID["EX02"].priorite == "P1"
    assert EXIGENCES_PAR_ID["EX17"].priorite == "P3"
    assert EXIGENCES_PAR_ID["EX13"].priorite == "P2"
    assert {e.priorite for e in EXIGENCES} == {"P1", "P2", "P3"}


def test_chaque_exigence_est_couverte_par_au_moins_un_test(request):
    items = request.session.items
    if not suite_complete(items):
        pytest.skip("exécution partielle de la suite : traçabilité non évaluable")
    couvertes = {i for item in items for m in item.iter_markers("exigence") for i in m.args}
    assert {e.id for e in EXIGENCES} - couvertes == set()


def test_plan_de_test_reference_des_exigences_et_des_tests_existants(request):
    items = request.session.items
    if not suite_complete(items):
        pytest.skip("exécution partielle de la suite : plan non évaluable")
    fonctions = {item.originalname or item.name for item in items}
    for cas in PLAN:
        assert set(cas.exigences) <= set(EXIGENCES_PAR_ID), cas.id
        assert set(cas.tests) <= fonctions, (cas.id, set(cas.tests) - fonctions)
    assert {e for cas in PLAN for e in cas.exigences} == set(EXIGENCES_PAR_ID)
    assert len({cas.id for cas in PLAN}) == len(PLAN)


# --- Conformité du dépôt (EX18) ---------------------------------------------------------
def charger_workflow() -> dict:
    return yaml.safe_load(
        (RACINE / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    )


@pytest.mark.exigence("EX18")
def test_workflow_ci_conforme():
    workflow = charger_workflow()
    declencheurs = workflow.get("on") or workflow.get(True)  # PyYAML lit « on » comme un booléen
    assert "pull_request" in declencheurs and "workflow_dispatch" in declencheurs
    etapes = [e for job in workflow["jobs"].values() for e in job["steps"]]
    commandes = "\n".join(e.get("run", "") for e in etapes)
    utilises = [e.get("uses", "") for e in etapes]
    assert any(u.startswith("actions/checkout@") for u in utilises)
    assert any(u.startswith("actions/setup-python@") for u in utilises)
    assert "pip install -r requirements.txt" in commandes
    assert "ruff check" in commandes and "ruff format --check" in commandes
    assert "pytest" in commandes and "--cov=app" in commandes and "--cov-fail-under" in commandes
    assert "--cov-report=xml" in commandes and "--junitxml" in commandes
    televersement = [e for e in etapes if e.get("uses", "").startswith("actions/upload-artifact@")]
    assert televersement and televersement[0].get("if") == "always()"
    setup = next(e for e in etapes if e.get("uses", "").startswith("actions/setup-python@"))
    assert re.fullmatch(r"3\.\d+", str(setup["with"]["python-version"]))


@pytest.mark.exigence("EX18")
def test_requirements_figees():
    lignes = [
        ligne.strip()
        for ligne in (RACINE / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if ligne.strip() and not ligne.startswith("#")
    ]
    assert lignes and all(
        re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", ligne) for ligne in lignes
    ), lignes
    paquets = {ligne.split("==")[0].lower() for ligne in lignes}
    assert {"fastapi", "scikit-learn", "pytest", "pytest-cov", "ruff", "httpx2"} <= paquets


@pytest.mark.exigence("EX18")
def test_arborescence_conforme_a_l_enonce():
    attendus = [
        "app/main.py",
        "app/validation.py",
        "app/preprocessing.py",
        "app/prediction.py",
        "tests/test_validation.py",
        "tests/test_api.py",
        "tests/test_integration.py",
        "tests/test_robustness.py",
        "tests/test_regression.py",
        "reports",
        ".github/workflows/tests.yml",
        "requirements.txt",
        ".gitignore",
        "README.md",
        "model/credit_risk_v1.0.0.joblib",
        "model/credit_risk_v1.0.0.json",
        "data/DONNEES.md",
    ]
    assert [chemin for chemin in attendus if not (RACINE / chemin).exists()] == []


@pytest.mark.exigence("EX18")
def test_gitignore_exclut_les_artefacts_generes():
    contenu = (RACINE / ".gitignore").read_text(encoding="utf-8")
    for motif in ("__pycache__", ".pytest_cache", ".ruff_cache", ".venv", ".coverage", "htmlcov"):
        assert motif in contenu


@pytest.mark.exigence("EX18")
def test_readme_documente_les_commandes_locales():
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    for commande in (
        "pip install -r requirements.txt",
        "pytest",
        "ruff check",
        "--cov",
        "uvicorn app.main:app",
        "DEMO_ECHEC=1",
        "locust",
    ):
        assert commande in readme, commande
