"""Non-régression : compare la référence v1.0.0 à trois candidats, puis le code v0.1 au code v0.2.

Les candidats sont réentraînés sur le jeu d'entraînement figé et évalués sur le jeu d'évaluation figé,
avec les tolérances de tests/reference/tolerances.json (définies avant cette comparaison).

Usage : python -m scripts.comparer_versions
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from app import config
from ml.comparaison import charger_json, charger_tolerances, comparer
from ml.donnees import CIBLE
from ml.entrainement import entrainer, probabilites_defaut
from ml.evaluation import metriques

REFERENCE = config.RACINE / "tests" / "reference"
RAPPORTS = config.RACINE / "reports"
CANDIDATS = [
    ("v1.0.1", "Équivalent", "Régression logistique, régularisation C = 0,5 (au lieu de 1,0)", {"c": 0.5}),
    ("v1.1.0", "Amélioré", "Arbre de gradient (modèle non linéaire)", {"algorithme": "hgb"}),
    ("v1.2.0", "Dégradé", "Régression logistique sur-régularisée, C = 0,0005", {"c": 0.0005}),
]  # fmt: skip


def regression_logicielle() -> dict:
    """Tests réussis par v0.1 qui échouent en v0.2 (doit être vide) et tests corrigés."""
    lire = lambda nom: {  # noqa: E731
        t["test"]: t["resultat"]
        for t in json.loads((RAPPORTS / nom / "resultats_tests.json").read_text(encoding="utf-8"))[
            "tests"
        ]
    }
    avant, apres = lire("campagne1_v0.1"), lire("campagne2_v0.2")
    regressions = sorted(t for t, r in avant.items() if r == "passed" and apres.get(t) != "passed")
    corriges = [t for t, r in avant.items() if r == "failed" and apres.get(t) == "passed"]
    return {
        "reussis_v0_1": sum(r == "passed" for r in avant.values()),
        "echecs_v0_1": sum(r == "failed" for r in avant.values()),
        "reussis_v0_2": sum(r == "passed" for r in apres.values()),
        "echecs_v0_2": sum(r == "failed" for r in apres.values()),
        "regressions_introduites": regressions,
        "tests_corriges": len(corriges),
    }


def main() -> None:
    entrainement = pd.read_csv(config.RACINE / "data" / "jeu_entrainement.csv")
    evaluation = pd.read_csv(config.RACINE / "data" / "jeu_evaluation.csv")
    baseline = charger_json(REFERENCE / "baseline_v1.0.0.json")
    cas_dores = charger_json(REFERENCE / "cas_dores.json")
    tolerances = charger_tolerances()
    entrees_dorees = pd.DataFrame([c["entree"] for c in cas_dores])

    sorties = []
    for version, nature, description, options in CANDIDATS:
        pipeline = entrainer(entrainement, **options)
        mesures = metriques(evaluation[CIBLE], probabilites_defaut(pipeline, evaluation))
        dores = list(probabilites_defaut(pipeline, entrees_dorees))
        sorties.append(
            {
                "version": version,
                "nature": nature,
                "description": description,
                "metriques": mesures,
                "comparaison": comparer(
                    baseline["metriques"], mesures, tolerances, cas_dores, dores
                ),
            }
        )
    resultat = {
        "date": date.today().isoformat(),
        "reference": {"version": baseline["version_modele"], "metriques": baseline["metriques"]},
        "tolerances": tolerances,
        "candidats": sorties,
        "regression_logicielle": regression_logicielle(),
    }
    (RAPPORTS / "non_regression.json").write_text(
        json.dumps(resultat, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (RAPPORTS / "non_regression.md").write_text(rapport_markdown(resultat), encoding="utf-8")
    for s in sorties:
        print(s["version"], s["comparaison"]["verdict"])


def _pct(x: float) -> str:
    return f"{x:.3f}"


def rapport_markdown(r: dict) -> str:
    ref = r["reference"]["metriques"]
    tol = r["tolerances"]["metriques"]
    lignes = [
        f"# Rapport de non-régression ({r['date']})",
        "",
        f"Référence : modèle v{r['reference']['version']} ; jeu d'évaluation figé ({ref['n']} demandes, "
        f"{ref['taux_defaut']:.1%} de défauts) ; seuil de décision {ref['seuil']}.",
        "",
        "## Tolérances (définies avant la comparaison)",
        "",
        "| Métrique | Critique | Baisse max. | Hausse max. | Plancher absolu |",
        "|---|---|---|---|---|",
    ]
    for nom, regle in tol.items():
        lignes.append(
            f"| {nom} | {'oui' if regle.get('critique') else 'non'} | {regle.get('baisse_max_absolue', '-')} "
            f"| {regle.get('hausse_max_absolue', '-')} | {regle.get('plancher_absolu', '-')} |"
        )
    lignes += [
        f"| cas dorés (écart de probabilité) | - | {r['tolerances']['cas_dores']['ecart_probabilite_max']} | - | - |",
        "",
        "## Comparaison par métrique",
        "",
        "| Métrique | Référence | "
        + " | ".join(f"{c['version']} ({c['nature'].lower()})" for c in r["candidats"])
        + " |",
        "|---|---|" + "---|" * len(r["candidats"]),
    ]
    for nom in tol:
        cellules = []
        for c in r["candidats"]:
            controle = next(
                x for x in c["comparaison"]["controles_metriques"] if x["metrique"] == nom
            )
            cellules.append(
                f"{_pct(controle['candidat'])} ({controle['ecart']:+.3f}) {controle['statut']}"
            )
        lignes.append(f"| {nom} | {_pct(ref[nom])} | " + " | ".join(cellules) + " |")
    lignes += [
        "",
        "## Verdicts",
        "",
        "| Version | Nature | Description | Verdict | Cas dorés hors tolérance | Écart max. | Changements de niveau |",
        "|---|---|---|---|---|---|---|",
    ]  # noqa: E501
    for c in r["candidats"]:
        d = c["comparaison"]["cas_dores"]
        lignes.append(
            f"| {c['version']} | {c['nature']} | {c['description']} | **{c['comparaison']['verdict']}** "
            f"| {d['nb_hors_tolerance']}/{len(d['cas'])} | {d['ecart_absolu_max']:.3f} | {d['nb_changements_niveau']} |"
        )
    lignes += ["", "## Détail des cas dorés hors tolérance", ""]
    for c in r["candidats"]:
        hors = [x for x in c["comparaison"]["cas_dores"]["cas"] if x["hors_tolerance"]]
        lignes.append(
            f"**{c['version']}** : "
            + (", ".join(f"{x['id']} ({x['ecart']:+.3f})" for x in hors) or "aucun")
        )
        lignes.append("")
    rl = r["regression_logicielle"]
    lignes += [
        "## Non-régression logicielle (code v0.1 -> v0.2)",
        "",
        f"- Tests réussis : {rl['reussis_v0_1']} (v0.1) -> {rl['reussis_v0_2']} (v0.2) ; échecs : {rl['echecs_v0_1']} -> {rl['echecs_v0_2']}.",
        f"- Tests réussis en v0.1 qui échouent en v0.2 : **{len(rl['regressions_introduites'])}**.",
        f"- Tests en échec en v0.1 corrigés en v0.2 : {rl['tests_corriges']}.",
        "",
    ]
    return "\n".join(lignes)


if __name__ == "__main__":
    main()
