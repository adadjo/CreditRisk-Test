"""Figures du rapport de qualification issues de l'audit par segment (données synthétiques).

Quatre figures :
  - faux_negatifs_par_segment.png : taux de faux négatifs par profil, face à l'ensemble ;
  - effet_du_seuil.png            : rappel par profil et part de dossiers signalés selon le seuil ;
  - calibration.png               : probabilité prédite et fréquence observée (diagramme de fiabilité) ;
  - echecs_par_anomalie.png       : tests en échec en v0.1 par cause racine, critiques en évidence.
Les trois premières sont lues dans reports/audit_segments.json, la dernière dans
reports/registre_anomalies.json.

Usage : python -m scripts.figures_qualification
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from scripts.style_graphiques import (
    AXE,
    BLEU,
    ENCRE,
    ENCRE_ATTENUEE,
    ENCRE_SECONDAIRE,
    GRIS_CONTEXTE,
    LARGEUR,
    ORANGE,
    SURFACE,
    TURQUOISE,
    appliquer_style,
    enregistrer,
    pourcent,
    virgule,
)

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "reports" / "figures"

LIBELLES = {
    "18-24 ans": "Âge 18–24 ans",
    "25-34 ans": "Âge 25–34 ans",
    "35-49 ans": "Âge 35–49 ans",
    "< 2 ans": "Ancienneté < 2 ans",
    "2-5 ans": "Ancienneté 2–5 ans",
    ">= 24 mois": "Durée ≥ 24 mois",
    "< 120 k FCFA": "Revenu < 120 k FCFA",
    "120-250 k FCFA": "Revenu 120–250 k FCFA",
    "> 250 k FCFA": "Revenu > 250 k FCFA",
}


def libelle(segment: str, court: bool = False) -> str:
    parties = [LIBELLES.get(p, p) for p in segment.split(" & ")]
    return (" +\n" if not court else " + ").join(parties)


def figure_faux_negatifs(audit: dict, chemin: Path) -> None:
    glob = audit["global"]
    segments = sorted(audit["pires_segments"], key=lambda s: s["taux_faux_negatifs"])
    lignes = [(libelle(s["segment"]), s["taux_faux_negatifs"], s["defauts"]) for s in segments]
    lignes.append(("Ensemble des demandes", glob["taux_faux_negatifs"], glob["vp"] + glob["fn"]))
    fig, ax = plt.subplots(figsize=(LARGEUR, 4.9))
    ys = list(range(len(lignes)))
    for y, (nom, taux, defauts) in zip(ys, lignes, strict=True):
        ensemble = nom.startswith("Ensemble")
        ax.barh(
            y,
            taux,
            height=0.62,
            color=GRIS_CONTEXTE if ensemble else ORANGE,
            edgecolor=SURFACE,
            linewidth=1.2,
            zorder=3,
        )
        ax.text(
            taux + 0.012,
            y,
            f"{pourcent(taux)}  ·  {defauts} défauts",
            va="center",
            fontsize=8.6,
            color=ENCRE,
        )
    ax.axvline(
        glob["taux_faux_negatifs"], color=ENCRE, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2
    )
    ax.set_yticks(ys, [nom for nom, _, _ in lignes], fontsize=8.2)
    ax.set_xlim(0, 1.22)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0], ["0 %", "20 %", "40 %", "60 %", "80 %", "100 %"])
    ax.set_xlabel(
        f"Part des défauts réels classés « faible » (seuil de décision {virgule(audit['seuil_decision'], 2)})"
    )
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    pire = max(taux for _, taux, _ in lignes)
    ax.set_title(
        f"Faux négatifs par profil : jusqu'à {pourcent(pire)} des défauts non signalés", pad=10
    )
    ax.text(
        glob["taux_faux_negatifs"] + 0.006,
        len(lignes) - 0.42,
        "moyenne de l'ensemble",
        fontsize=7.8,
        color=ENCRE_SECONDAIRE,
        va="bottom",
    )
    enregistrer(fig, chemin)


def figure_seuil(audit: dict, chemin: Path) -> None:
    balayage = audit["balayage_seuils"]
    seuils = [b["seuil"] for b in balayage]
    series = [
        ("Ensemble", "rappel", BLEU),
        ("Durée ≥ 24 mois", "rappel[>= 24 mois]", ORANGE),
        ("Ancienneté < 2 ans + durée ≥ 24 mois", "rappel[< 2 ans & >= 24 mois]", TURQUOISE),
    ]
    fig, (gauche, droite) = plt.subplots(
        1, 2, figsize=(LARGEUR, 3.5), gridspec_kw={"width_ratios": [1.45, 1]}
    )
    for _nom, cle, couleur in series:
        valeurs = [b[cle] for b in balayage]
        gauche.plot(seuils, valeurs, color=couleur, linewidth=2.0, zorder=3)
        gauche.scatter(
            seuils, valeurs, s=26, color=couleur, edgecolor=SURFACE, linewidth=1.2, zorder=4
        )
    gauche.axvline(
        audit["seuil_decision"], color=ENCRE, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2
    )
    gauche.text(
        audit["seuil_decision"] + 0.006,
        1.02,
        "seuil actuel 0,30",
        fontsize=7.8,
        color=ENCRE_SECONDAIRE,
        va="bottom",
    )
    gauche.set_ylim(0, 1.0)
    gauche.set_xlim(0.08, 0.52)
    gauche.set_xticks([0.1, 0.2, 0.3, 0.4, 0.5], ["0,1", "0,2", "0,3", "0,4", "0,5"])
    gauche.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0 %", "25 %", "50 %", "75 %", "100 %"])
    gauche.set_xlabel("Seuil de décision (probabilité à partir de laquelle un dossier est signalé)")
    gauche.set_title("Rappel : défauts détectés", pad=14)
    droite.plot(
        seuils, [b["part_dossiers_signales"] for b in balayage], color=BLEU, linewidth=2.0, zorder=3
    )
    droite.scatter(
        seuils,
        [b["part_dossiers_signales"] for b in balayage],
        s=26,
        color=BLEU,
        edgecolor=SURFACE,
        linewidth=1.2,
        zorder=4,
    )
    droite.axvline(
        audit["seuil_decision"], color=ENCRE, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2
    )
    droite.set_ylim(0, 1.0)
    droite.set_xlim(0.08, 0.52)
    droite.set_xticks([0.1, 0.2, 0.3, 0.4, 0.5], ["0,1", "0,2", "0,3", "0,4", "0,5"])
    droite.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0 %", "25 %", "50 %", "75 %", "100 %"])
    droite.set_xlabel("Seuil de décision")
    droite.set_title("Charge : dossiers signalés", pad=14)
    legende = [
        Line2D([], [], color=c, linewidth=2.0, marker="o", markersize=5) for _, _, c in series
    ]
    fig.legend(
        legende,
        [nom for nom, _, _ in series],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.07),
        ncol=3,
        handletextpad=0.4,
        columnspacing=1.4,
    )
    fig.tight_layout(w_pad=2.0)
    enregistrer(fig, chemin)


def figure_calibration(audit: dict, chemin: Path) -> None:
    tranches = audit["calibration"]
    x = [t["probabilite_moyenne"] for t in tranches]
    y = [t["frequence_observee"] for t in tranches]
    fig, ax = plt.subplots(figsize=(LARGEUR * 0.62, 3.6))
    ax.plot([0, 1], [0, 1], color=AXE, linewidth=1.4, zorder=2)
    ax.plot(x, y, color=BLEU, linewidth=2.0, zorder=3)
    ax.scatter(x, y, s=34, color=BLEU, edgecolor=SURFACE, linewidth=1.4, zorder=4)
    ax.text(
        0.80,
        0.655,
        "calibration parfaite",
        rotation=45,
        fontsize=7.8,
        color=ENCRE_ATTENUEE,
        ha="center",
        va="center",
    )
    ax.text(
        0.04,
        0.93,
        f"Erreur de calibration moyenne : {virgule(audit['ece'], 3)}",
        fontsize=8.6,
        color=ENCRE,
        va="top",
    )
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "0,25", "0,5", "0,75", "1"])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "0,25", "0,5", "0,75", "1"])
    ax.set_xlabel("Probabilité de défaut prédite (moyenne par tranche)")
    ax.set_ylabel("Fréquence de défaut observée")
    ax.set_title("Calibration : des probabilités globalement fiables", pad=10)
    ax.set_aspect("equal")
    enregistrer(fig, chemin)


COURTS = {
    "A-01": "Entrée incomplète ou nulle (erreur 500)",
    "A-02": "Valeurs non finies ou démesurées (500)",
    "A-03": "Conversion implicite des types",
    "A-04": "Troncature silencieuse d'un entier",
    "A-05": "Bornes métier absentes ou incomplètes",
    "A-06": "Schéma non strict",
    "A-07": "Âge et ancienneté incohérents",
    "A-08": "JSON mal formé ou corps vide (500)",
    "A-09": "Type de contenu non vérifié",
    "A-10": "Aucune limite de taille ni de profondeur",
    "A-11": "Erreurs 500 qui exposent la trace",
    "A-12": "Modèle indisponible mal géré",
    "A-13": "Aucun contrôle d'intégrité du modèle",
    "A-14": "Prétraitement sans garde",
    "A-15": "Aucune garde sur la sortie du modèle",
    "A-16": "Version du modèle incohérente",
    "A-17": "/model-info expose le chemin du modèle",
    "A-18": "Contrat d'API incomplet (404, 405, OpenAPI)",
    "A-19": "Seuil de risque élevé mal appliqué",
    "A-20": "Alertes hors domaine non implémentées",
}


def figure_echecs_par_anomalie(registre: dict, chemin: Path) -> None:
    lignes = sorted(
        (
            (a["id"], a["gravite"], a["tests"]["echecs_v0_1"])
            for a in registre["anomalies"]
            if a["tests"]["echecs_v0_1"] > 0
        ),
        key=lambda ligne: ligne[2],
    )
    fig, ax = plt.subplots(figsize=(LARGEUR, 5.6))
    for y, (_identifiant, gravite, echecs) in enumerate(lignes):
        ax.barh(
            y,
            echecs,
            height=0.66,
            color=ORANGE if gravite == "Critique" else BLEU,
            edgecolor=SURFACE,
            linewidth=1.2,
            zorder=3,
        )
        ax.text(echecs + 1.0, y, str(echecs), va="center", fontsize=8.4, color=ENCRE)
    ax.set_yticks(
        range(len(lignes)),
        [f"{identifiant}  {COURTS[identifiant]}" for identifiant, _, _ in lignes],
        fontsize=8.0,
    )
    ax.set_xlim(0, max(e for _, _, e in lignes) * 1.12)
    ax.set_xlabel("Tests de la suite en échec sur la v0.1 (un test rattaché à une seule cause)")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Le nombre de tests en échec n'est pas la gravité", pad=10)
    legende = [
        Line2D([], [], color=ORANGE, linewidth=8, label="Gravité critique"),
        Line2D([], [], color=BLEU, linewidth=8, label="Gravité majeure ou moyenne"),
    ]
    ax.legend(handles=legende, loc="lower right", frameon=False, fontsize=8.2)
    enregistrer(fig, chemin)


def main() -> None:
    appliquer_style()
    audit = json.loads((RACINE / "reports" / "audit_segments.json").read_text(encoding="utf-8"))
    DOSSIER.mkdir(parents=True, exist_ok=True)
    figure_faux_negatifs(audit, DOSSIER / "faux_negatifs_par_segment.png")
    figure_seuil(audit, DOSSIER / "effet_du_seuil.png")
    figure_calibration(audit, DOSSIER / "calibration.png")
    registre = json.loads(
        (RACINE / "reports" / "registre_anomalies.json").read_text(encoding="utf-8")
    )
    figure_echecs_par_anomalie(registre, DOSSIER / "echecs_par_anomalie.png")
    print("figures écrites dans", DOSSIER)


if __name__ == "__main__":
    main()
