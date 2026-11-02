"""Campagne de test : exécution de pytest, rejeu des scénarios de l'API, génération des documents.

Usage (depuis la racine du dépôt) :
    python -m scripts.campagne executer reports/campagne2_v0.2 --etiquette v0.2
    python -m scripts.campagne documents
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path

from app import config

RAPPORTS = config.RACINE / "reports"
BIBLIOTHEQUES = ("fastapi", "starlette", "scikit-learn", "numpy", "pandas", "pytest", "ruff")


def _version_git() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=config.RACINE,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "non versionné"


def rejouer_scenarios() -> list[dict]:
    """Rejoue les scénarios fonctionnels de l'API et décrit chaque résultat observé."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.prediction import ServicePrediction
    from tests.scenarios import SCENARIOS_API, executer_scenario

    absent = RAPPORTS / "_tmp" / "modele_absent.joblib"
    clients = {
        "normal": TestClient(create_app(), raise_server_exceptions=False),
        "sans_modele": TestClient(
            create_app(ServicePrediction(absent, absent.with_suffix(".json"))),
            raise_server_exceptions=False,
        ),
    }
    lignes = []
    for s in sorted(SCENARIOS_API, key=lambda x: x.id):
        observe = executer_scenario(s, clients)
        texte = observe["texte"]
        manquants = [d for d in s.details if d not in observe["details_observes"]]
        lignes.append(
            {
                "id": s.id,
                "titre": s.titre,
                "exigences": list(s.exigences),
                "requete": f"{s.methode} {s.chemin}",
                "statut_attendu": s.statut_attendu,
                "statut_observe": observe["statut_observe"],
                "erreur_attendue": s.code_erreur,
                "erreur_observee": observe["erreur_observee"],
                "details_manquants": [list(d) for d in manquants],
                "contenu_attendu": s.contenu_attendu,
                "comportement": s.comportement,
                "fuite_technique": any(
                    m in texte for m in ("Traceback", 'File "', "/home/", ".py")
                ),
                "conforme": observe["conforme"],
                "extrait_reponse": texte[:160],
            }
        )
    return lignes


MOTS_SENSIBLES = (
    "secret",
    "Traceback",
    "RuntimeError",
    "ValueError",
    "/srv",
    ".py",
    'File "',
    "/home/",
)


def _sonder(identifiant, description, attendu, reponse, extra=None) -> dict:
    """Résume la réponse observée face à une panne injectée et la compare à l'attendu."""
    try:
        corps = reponse.json()
    except ValueError:
        corps = {}
    erreur = corps.get("erreur") if isinstance(corps, dict) else None
    statut_attendu, code_attendu = attendu
    fuite = any(mot in reponse.text for mot in MOTS_SENSIBLES)
    probabilite = corps.get("probabilite_defaut") if isinstance(corps, dict) else None
    ligne = {
        "id": identifiant,
        "description": description,
        "statut_attendu": statut_attendu,
        "erreur_attendue": code_attendu,
        "statut_observe": reponse.status_code,
        "erreur_observee": erreur,
        "fuite_technique": fuite,
        "probabilite_renvoyee": probabilite,
    }
    ligne["conforme"] = (
        reponse.status_code == statut_attendu and erreur == code_attendu and not fuite
        and (statut_attendu == 200 or probabilite is None)
    )  # fmt: skip
    ligne.update(extra or {})
    return ligne


def rejouer_pannes() -> list[dict]:
    """Injecte les pannes de l'activité 3 (modèle, prétraitement, dimensions, prédiction)."""
    import logging
    import tempfile
    from types import SimpleNamespace
    from unittest.mock import patch

    import numpy as np
    from fastapi.testclient import TestClient

    from app import preprocessing, validation
    from app.main import create_app
    from app.prediction import ServicePrediction
    from app.preprocessing import ErreurPretraitement
    from tests.scenarios import PAYLOAD_VALIDE
    from tests.test_integration import DEFAUTS_MODELE, FauxModele, preparer_modele_defectueux

    logging.disable(logging.CRITICAL)
    sorties: list[dict] = []
    libelles = {
        "fichier_absent": "Fichier modèle absent",
        "octets_aleatoires": "Fichier modèle illisible (octets aléatoires)",
        "fichier_altere": "Fichier modèle altéré (un octet modifié)",
        "objet_non_conforme": "Fichier contenant un objet qui n'est pas un modèle",
        "modele_a_5_variables": "Modèle entraîné sur 5 variables au lieu de 6",
        "metadonnees_incompletes": "Métadonnées incomplètes (clé version absente)",
        "metadonnees_illisibles": "Métadonnées illisibles (JSON invalide)",
        "variables_divergentes": "Variables des métadonnées dans un autre ordre",
        "metadonnees_absentes": "Fichier de métadonnées absent",
        "modele_substitue": "Autre modèle valide (6 variables) sous le nom du modèle versionné",
        "octets_ajoutes": "Octets ajoutés en fin de fichier (le fichier reste chargeable)",
        "empreinte_metadonnees_erronee": "Empreinte SHA-256 des métadonnées erronée",
    }
    for defaut in DEFAUTS_MODELE:
        with tempfile.TemporaryDirectory() as dossier:
            modele, meta = preparer_modele_defectueux(Path(dossier), defaut)
            try:
                ServicePrediction(modele, meta).charger()
                chargement = "chargement accepté"
            except Exception as exc:  # noqa: BLE001 - on observe le type d'exception
                chargement = type(exc).__name__
            client = TestClient(
                create_app(ServicePrediction(modele, meta)), raise_server_exceptions=False
            )
            sante = client.get("/health").status_code
            reponse = client.post("/predict", json=PAYLOAD_VALIDE)
            sorties.append(
                _sonder(f"M-{defaut}", libelles[defaut], (503, "modele_indisponible"), reponse,
                        {"chargement": chargement, "statut_health": sante, "groupe": "chargement"})
            )  # fmt: skip

    service = ServicePrediction()
    service.charger()
    client = TestClient(create_app(service), raise_server_exceptions=False)

    def appeler(identifiant, description, attendu, groupe="pipeline"):
        reponse = client.post("/predict", json=PAYLOAD_VALIDE)
        sorties.append(_sonder(identifiant, description, attendu, reponse, {"groupe": groupe}))

    incomplete = SimpleNamespace(age=35, revenu_mensuel=250000.0, montant_credit=1e6, duree_mois=12)
    with patch.object(validation, "valider_demande", lambda _p: incomplete):
        appeler(
            "P-variable_absente",
            "Variable attendue absente après validation",
            (500, "erreur_pretraitement"),
        )

    def echec_controle(_d):
        raise ErreurPretraitement("secret /srv/app/pretraitement.py ligne 42")

    with patch.object(preprocessing, "construire_caracteristiques", echec_controle):
        appeler(
            "P-pretraitement_controle",
            "Le prétraitement signale une erreur",
            (500, "erreur_pretraitement"),
        )

    def echec_imprevu(_d):
        raise RuntimeError("secret : connexion /srv/db refusée")

    with patch.object(preprocessing, "construire_caracteristiques", echec_imprevu):
        appeler(
            "P-pretraitement_imprevu",
            "Exception imprévue dans le prétraitement",
            (500, "erreur_interne"),
        )

    for forme in ((1, 5), (1, 7), (2, 6)):
        with patch.object(
            preprocessing, "construire_caracteristiques", lambda _d, f=forme: np.zeros(f)
        ):
            appeler(
                f"D-{forme[0]}x{forme[1]}",
                f"Dimensions {forme} au lieu de (1, 6)",
                (500, "incoherence_dimensions"),
            )

    reel = service._modele
    try:
        service._modele = FauxModele(erreur=RuntimeError("secret interne du modèle /srv/m.py"))
        appeler(
            "P-prediction_exception",
            "Erreur interne pendant l'inférence",
            (500, "erreur_prediction"),
        )
        for nom, valeur in (
            ("nan", float("nan")),
            ("1.5", 1.5),
            ("-0.1", -0.1),
            ("inf", float("inf")),
        ):
            service._modele = FauxModele(probabilite=valeur)
            appeler(
                f"P-proba_{nom}",
                f"Le modèle renvoie la probabilité {nom}",
                (500, "erreur_prediction"),
            )
    finally:
        service._modele = reel
    logging.disable(logging.NOTSET)
    return sorties


def rejouer_fuzzing(n: int = 800) -> dict:
    """800 requêtes pseudo-aléatoires (graine 2026) : répartition des codes HTTP observés."""
    import logging
    from collections import Counter

    import numpy as np
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.scenarios import brut
    from tests.test_robustness import JSON, cas_fuzz

    logging.disable(logging.CRITICAL)
    client = TestClient(create_app(), raise_server_exceptions=False)
    rng = np.random.default_rng(2026)
    statuts: Counter = Counter()
    for _ in range(n):
        statuts[client.post("/predict", content=brut(cas_fuzz(rng)), headers=JSON).status_code] += 1
    logging.disable(logging.NOTSET)
    erreurs_serveur = sum(v for k, v in statuts.items() if k >= 500)
    return {
        "n": n,
        "statuts": {str(k): v for k, v in sorted(statuts.items())},
        "erreurs_serveur": erreurs_serveur,
        "taux_erreurs_serveur": round(erreurs_serveur / n, 4),
    }


def executer(dossier: Path, etiquette: str) -> int:
    dossier.mkdir(parents=True, exist_ok=True)
    commande = [
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        f"--resultats-json={dossier / 'resultats_tests.json'}",
        f"--junitxml={dossier / 'junit.xml'}",
        "--cov=app", "--cov=ml", f"--cov-report=json:{dossier / 'couverture.json'}",
        "--cov-report=term-missing",
    ]  # fmt: skip
    debut = datetime.now()
    processus = subprocess.run(commande, cwd=config.RACINE, capture_output=True, text=True)
    (dossier / "pytest_sortie.txt").write_text(
        processus.stdout + processus.stderr, encoding="utf-8"
    )
    (dossier / "resultats_api.json").write_text(
        json.dumps(rejouer_scenarios(), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (dossier / "pannes.json").write_text(
        json.dumps(rejouer_pannes(), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (dossier / "fuzzing.json").write_text(
        json.dumps(rejouer_fuzzing(), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    resultats = json.loads((dossier / "resultats_tests.json").read_text(encoding="utf-8"))["tests"]
    comptes = {
        r: sum(t["resultat"] == r for t in resultats) for r in ("passed", "failed", "skipped")
    }
    couverture = json.loads((dossier / "couverture.json").read_text(encoding="utf-8"))
    meta = {
        "etiquette": etiquette,
        "version_application": config.VERSION_APPLICATION,
        "commit_git": _version_git(),
        "debut": debut.isoformat(timespec="seconds"),
        "duree_s": round((datetime.now() - debut).total_seconds(), 1),
        "code_sortie_pytest": processus.returncode,
        "tests": {"total": len(resultats), **comptes},
        "couverture_pct": round(couverture["totals"]["percent_covered"], 2),
        "python": platform.python_version(),
        "systeme": platform.platform(),
        "bibliotheques": {nom: metadata.version(nom) for nom in BIBLIOTHEQUES},
    }
    (dossier / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: meta[k] for k in ("etiquette", "tests", "couverture_pct", "code_sortie_pytest")}
        )
    )
    return processus.returncode


# --- Documents ------------------------------------------------------------------------------
def _tableau(entetes: list[str], lignes: list[list[str]]) -> str:
    def nettoyer(cellule) -> str:
        return str(cellule).replace("|", "\\|").replace("\n", " ")

    sortie = ["| " + " | ".join(entetes) + " |", "|" + "|".join("---" for _ in entetes) + "|"]
    sortie += ["| " + " | ".join(nettoyer(c) for c in ligne) + " |" for ligne in lignes]
    return "\n".join(sortie)


def _comptes_par_exigence(dossier: Path) -> dict[str, tuple[int, int]]:
    """Exigence -> (tests réussis, tests exécutés hors ignorés)."""
    chemin = dossier / "resultats_tests.json"
    if not chemin.exists():
        return {}
    comptes: dict[str, list[int]] = {}
    for test in json.loads(chemin.read_text(encoding="utf-8"))["tests"]:
        if test["resultat"] == "skipped":
            continue
        for exigence in test["exigences"]:
            ok_et_total = comptes.setdefault(exigence, [0, 0])
            ok_et_total[0] += test["resultat"] == "passed"
            ok_et_total[1] += 1
    return {cle: (v[0], v[1]) for cle, v in comptes.items()}


def documents() -> None:
    from tests.exigences import EXIGENCES
    from tests.plan_de_test import PLAN

    campagnes = sorted(RAPPORTS.glob("campagne*_v*"))
    resultats = {c.name.split("_")[-1]: _comptes_par_exigence(c) for c in campagnes}

    plan = ["# Plan de test et matrice de traçabilité\n", "## Exigences, risques et priorités\n"]
    plan.append(
        _tableau(
            ["ID", "Exigence", "Résultat attendu", "Risque associé", "Gravité", "Probabilité", "Score", "Priorité"],
            [[e.id, e.intitule, e.resultat_attendu, e.risque, e.gravite, e.probabilite, e.score, e.priorite]
             for e in EXIGENCES],
        )
    )  # fmt: skip
    plan.append(
        "\nPriorité = gravité (Critique 4, Majeure 3, Moyenne 2, Mineure 1) x probabilité (Élevée 3, Moyenne 2, Faible 1) ; P1 si score >= 6, P2 de 3 à 5, P3 sinon.\n"
    )
    plan.append("## Cas de test\n")
    plan.append(
        _tableau(
            ["Cas", "Titre", "Exigences", "Niveau", "Priorité", "Préconditions", "Données d'entrée", "Résultat attendu"],
            [[c.id, c.titre, ", ".join(c.exigences), c.niveau, c.priorite, c.preconditions, c.donnees, c.attendu]
             for c in sorted(PLAN, key=lambda c: (c.priorite, c.id))],
        )
    )  # fmt: skip
    (RAPPORTS / "plan_de_test.md").write_text("\n".join(plan) + "\n", encoding="utf-8")

    etiquettes = sorted(resultats)
    entetes = ["ID", "Exigence", "Priorité", "Cas de test", "Fonctions pytest"] + [
        f"Réussis {e}" for e in etiquettes
    ]
    lignes = []
    for e in EXIGENCES:
        cas = [c for c in PLAN if e.id in c.exigences]
        fonctions = sorted({f for c in cas for f in c.tests})
        ligne = [e.id, e.intitule, e.priorite, ", ".join(c.id for c in cas), len(fonctions)]
        for etiquette in etiquettes:
            ok, total = resultats[etiquette].get(e.id, (0, 0))
            ligne.append(f"{ok}/{total}")
        lignes.append(ligne)
    matrice = "# Matrice de traçabilité\n\n" + _tableau(entetes, lignes) + "\n"
    (RAPPORTS / "matrice_tracabilite.md").write_text(matrice, encoding="utf-8")
    with (RAPPORTS / "matrice_tracabilite.csv").open("w", newline="", encoding="utf-8") as fichier:
        writer = csv.writer(fichier)
        writer.writerow(entetes)
        writer.writerows(lignes)
    print(f"documents écrits pour {etiquettes}")


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    sous = parseur.add_subparsers(dest="commande", required=True)
    cmd = sous.add_parser("executer")
    cmd.add_argument("dossier", type=Path)
    cmd.add_argument("--etiquette", required=True)
    sous.add_parser("documents")
    args = parseur.parse_args()
    if args.commande == "executer":
        executer(config.RACINE / args.dossier, args.etiquette)
    else:
        documents()


if __name__ == "__main__":
    main()
