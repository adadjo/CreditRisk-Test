"""Non-régression du modèle : comparaison d'une nouvelle version à la version de référence.

Les tolérances sont lues dans tests/reference/tolerances.json, fichier figé avant toute
comparaison. Trois verdicts sont possibles :
- CONFORME      : tous les contrôles sont dans la tolérance ;
- REVUE_REQUISE : aucun critère critique dégradé, mais un écart non critique ou une dérive
                  des cas dorés dépasse la tolérance (justification à documenter) ;
- REGRESSION    : un critère critique (rappel, F1) est dégradé au-delà de la tolérance
                  (investigation obligatoire, livraison bloquée).
"""

from __future__ import annotations

import json
from pathlib import Path

from app import config
from app.prediction import interpreter_probabilite

EPS = 1e-12
RACINE_REFERENCE = Path(__file__).resolve().parent.parent / "tests" / "reference"


def charger_json(chemin: Path | str) -> dict | list:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def charger_tolerances(chemin: Path | str | None = None) -> dict:
    return charger_json(chemin or RACINE_REFERENCE / "tolerances.json")


def evaluer_metriques(reference: dict, candidat: dict, tolerances: dict) -> list[dict]:
    """Un contrôle par métrique : écart observé, tolérance, statut OK / ECART / ECHEC."""
    controles = []
    for nom, regle in tolerances["metriques"].items():
        ref, cand = reference[nom], candidat[nom]
        ecart = cand - ref
        violations = []
        if "baisse_max_absolue" in regle and ecart < -regle["baisse_max_absolue"] - EPS:
            violations.append(f"baisse de {-ecart:.4f} > {regle['baisse_max_absolue']}")
        if "hausse_max_absolue" in regle and ecart > regle["hausse_max_absolue"] + EPS:
            violations.append(f"hausse de {ecart:.4f} > {regle['hausse_max_absolue']}")
        if "plancher_absolu" in regle and cand < regle["plancher_absolu"] - EPS:
            violations.append(f"valeur {cand:.4f} sous le plancher {regle['plancher_absolu']}")
        critique = bool(regle.get("critique"))
        statut = "OK" if not violations else ("ECHEC" if critique else "ECART")
        controles.append(
            {
                "metrique": nom,
                "reference": ref,
                "candidat": cand,
                "ecart": ecart,
                "critique": critique,
                "statut": statut,
                "detail": "; ".join(violations),
            }
        )
    return controles


def _proche_d_un_seuil(probabilite: float, marge: float) -> bool:
    seuils = (config.SEUIL_RISQUE_MODERE, config.SEUIL_RISQUE_ELEVE)
    return any(abs(probabilite - seuil) <= marge for seuil in seuils)


def evaluer_cas_dores(
    cas: list[dict], probabilites_candidat: list[float], tolerances: dict
) -> dict:
    """Compare les probabilités du candidat à celles de référence, cas par cas."""
    regle = tolerances["cas_dores"]
    lignes = []
    for cas_i, p_cand in zip(cas, probabilites_candidat, strict=True):
        p_ref = cas_i["probabilite_reference"]
        niveau_ref = interpreter_probabilite(p_ref).niveau
        niveau_cand = interpreter_probabilite(p_cand).niveau
        ecart = p_cand - p_ref
        changement = niveau_ref != niveau_cand and not _proche_d_un_seuil(
            p_ref, regle["marge_seuil"]
        )
        lignes.append(
            {
                "id": cas_i["id"],
                "p_reference": p_ref,
                "p_candidat": p_cand,
                "ecart": ecart,
                "niveau_reference": niveau_ref,
                "niveau_candidat": niveau_cand,
                "hors_tolerance": abs(ecart) > regle["ecart_probabilite_max"] + EPS,
                "changement_niveau_injustifie": changement,
            }
        )
    return {
        "ecart_absolu_max": max(abs(ligne["ecart"]) for ligne in lignes),
        "nb_hors_tolerance": sum(ligne["hors_tolerance"] for ligne in lignes),
        "nb_changements_niveau": sum(ligne["changement_niveau_injustifie"] for ligne in lignes),
        "cas": lignes,
    }


def comparer(
    metriques_reference: dict,
    metriques_candidat: dict,
    tolerances: dict,
    cas_dores: list[dict] | None = None,
    probabilites_dorees_candidat: list[float] | None = None,
) -> dict:
    controles = evaluer_metriques(metriques_reference, metriques_candidat, tolerances)
    dores = None
    if cas_dores is not None and probabilites_dorees_candidat is not None:
        dores = evaluer_cas_dores(cas_dores, probabilites_dorees_candidat, tolerances)
    if any(c["statut"] == "ECHEC" for c in controles):
        verdict = "REGRESSION"
    elif any(c["statut"] == "ECART" for c in controles) or (
        dores and (dores["nb_hors_tolerance"] or dores["nb_changements_niveau"])
    ):
        verdict = "REVUE_REQUISE"
    else:
        verdict = "CONFORME"
    return {"verdict": verdict, "controles_metriques": controles, "cas_dores": dores}
