"""Audit des faux négatifs par profil de demandeur (modèle de référence, jeu d'évaluation figé).

Données SYNTHÉTIQUES : l'audit démontre la méthode et l'écart entre performance globale et
performance par segment ; il ne mesure aucune équité réelle.

Usage : python -m scripts.audit_segments
"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from app import config
from ml.donnees import CIBLE
from ml.entrainement import probabilites_defaut
from ml.evaluation import SEUIL_DECISION, audit_segments, metriques

RAPPORTS = config.RACINE / "reports"
SEUILS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
SEGMENTS_CLES = ["Ensemble", "< 2 ans", ">= 24 mois", "< 2 ans & >= 24 mois", "18-24 ans"]
MIN_DEFAUTS = 30


def calibration(y, p, classes: int = 10) -> pd.DataFrame:
    bornes = np.linspace(0, 1, classes + 1)
    indices = np.clip(np.digitize(p, bornes[1:-1]), 0, classes - 1)
    lignes = []
    for i in range(classes):
        masque = indices == i
        if masque.sum():
            lignes.append(
                {
                    "tranche": f"[{bornes[i]:.1f} ; {bornes[i + 1]:.1f}[",
                    "n": int(masque.sum()),
                    "probabilite_moyenne": float(p[masque].mean()),
                    "frequence_observee": float(y[masque].mean()),
                }
            )
    return pd.DataFrame(lignes)


def main() -> None:
    evaluation = pd.read_csv(config.RACINE / "data" / "jeu_evaluation.csv")
    p = probabilites_defaut(joblib.load(config.CHEMIN_MODELE), evaluation)
    y = evaluation[CIBLE].to_numpy()

    audit = audit_segments(evaluation, p, SEUIL_DECISION)
    audit.to_csv(RAPPORTS / "audit_segments.csv", index=False)
    globale = metriques(y, p)
    candidats = audit[(audit.defauts >= MIN_DEFAUTS) & (audit.segment != "Ensemble")]
    pires = candidats.sort_values("taux_faux_negatifs", ascending=False).head(8)

    balayage = []
    for seuil in SEUILS:
        ligne = {"seuil": seuil}
        m = metriques(y, p, seuil)
        ligne.update(
            rappel=m["rappel"], precision=m["precision"], f1=m["f1"],
            part_dossiers_signales=float((p >= seuil).mean()),
        )  # fmt: skip
        a = audit_segments(evaluation, p, seuil).set_index("segment")
        for nom in SEGMENTS_CLES[1:]:
            ligne[f"rappel[{nom}]"] = float(a.loc[nom, "rappel"])
        balayage.append(ligne)
    balayage = pd.DataFrame(balayage)

    calib = calibration(y, p)
    ece = float(
        (calib.n * (calib.probabilite_moyenne - calib.frequence_observee).abs()).sum()
        / calib.n.sum()
    )
    resume = {
        "seuil_decision": SEUIL_DECISION,
        "global": globale,
        "segments_cles": audit[audit.segment.isin(SEGMENTS_CLES)].to_dict("records"),
        "pires_segments": pires.to_dict("records"),
        "balayage_seuils": balayage.to_dict("records"),
        "calibration": calib.to_dict("records"),
        "ece": ece,
        "min_defauts": MIN_DEFAUTS,
    }
    (RAPPORTS / "audit_segments.json").write_text(
        json.dumps(resume, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    md = ["# Audit des faux négatifs par profil (données synthétiques)", ""]
    md.append(
        f"Modèle v1.0.0, jeu d'évaluation figé ({len(evaluation)} demandes), seuil de décision {SEUIL_DECISION} : "
        f"rappel global {globale['rappel']:.3f}, taux de faux négatifs global {globale['taux_faux_negatifs']:.3f}."
    )
    md += ["", "## Segments les plus exposés (au moins 30 défauts)", ""]
    md.append(
        pires[["segment", "n", "defauts", "faux_negatifs", "rappel", "taux_faux_negatifs"]]
        .round(3)
        .to_markdown(index=False)
    )
    md += ["", "## Effet du seuil de décision", ""]
    md.append(balayage.round(3).to_markdown(index=False))
    md += ["", f"## Calibration (erreur moyenne pondérée {ece:.3f})", ""]
    md.append(calib.round(3).to_markdown(index=False))
    (RAPPORTS / "audit_segments.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(
        pires[["segment", "n", "defauts", "rappel", "taux_faux_negatifs"]]
        .round(3)
        .to_string(index=False)
    )
    print(balayage.round(3).to_string(index=False))
    print("ECE", round(ece, 3))


if __name__ == "__main__":
    main()
