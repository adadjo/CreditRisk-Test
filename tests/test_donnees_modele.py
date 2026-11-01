"""Tests unitaires du jeu synthétique, de l'entraînement, des métriques et de l'audit par segments."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app import config
from app.prediction import ServicePrediction, calculer_empreinte
from app.validation import valider_demande
from ml import donnees as d
from ml.entrainement import (
    domaine_entrainement,
    entrainer,
    probabilites_defaut,
    sauvegarder_modele,
)
from ml.evaluation import audit_segments, metriques

DATA = config.RACINE / "data"
ENTRAINEMENT = pd.read_csv(DATA / "jeu_entrainement.csv")
EVALUATION = pd.read_csv(DATA / "jeu_evaluation.csv")


@pytest.mark.exigence("EX13")
def test_generateur_deterministe_pour_une_graine_donnee():
    a, b = d.generer_donnees(500, graine=1), d.generer_donnees(500, graine=1)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(d.generer_donnees(500, graine=2))


@pytest.mark.exigence("EX13", "EX07")
def test_jeux_figes_identiques_a_la_regeneration():
    entrainement, evaluation = d.separer_entrainement_evaluation(d.generer_donnees())
    pd.testing.assert_frame_equal(entrainement, ENTRAINEMENT, check_dtype=False)
    pd.testing.assert_frame_equal(evaluation, EVALUATION, check_dtype=False)


@pytest.mark.exigence("EX01", "EX02", "EX03", "EX08", "EX12")
def test_toutes_les_lignes_synthetiques_sont_des_demandes_valides():
    for jeu in (ENTRAINEMENT, EVALUATION):
        for ligne in jeu[d.COLONNES_ENTREE].to_dict("records"):
            valider_demande(ligne)


def test_structure_du_jeu_sans_valeur_manquante():
    for jeu in (ENTRAINEMENT, EVALUATION):
        assert list(jeu.columns) == [*d.COLONNES_ENTREE, d.CIBLE]
        assert not jeu.isna().any().any()
        assert set(jeu[d.CIBLE].unique()) == {0, 1}


def test_decoupage_stratifie_et_taux_de_defaut():
    assert len(ENTRAINEMENT) == 9000 and len(EVALUATION) == 3000
    assert abs(ENTRAINEMENT[d.CIBLE].mean() - EVALUATION[d.CIBLE].mean()) < 0.001
    assert 0.18 <= ENTRAINEMENT[d.CIBLE].mean() <= 0.27


def test_interaction_cachee_presente_dans_les_donnees():
    complet = pd.concat([ENTRAINEMENT, EVALUATION])
    segment = (complet.anciennete_activite < 2) & (complet.duree_mois >= 24)
    assert complet.loc[segment, d.CIBLE].mean() > 1.5 * complet.loc[~segment, d.CIBLE].mean()


def test_metriques_sur_un_exemple_calcule_a_la_main():
    y = [1, 1, 0, 0, 1, 0]
    p = [0.9, 0.2, 0.4, 0.1, 0.35, 0.5]  # seuil 0,30 -> prédits : 1 0 1 0 1 1
    m = metriques(y, p, seuil=0.30)
    assert (m["vp"], m["fn"], m["fp"], m["vn"]) == (2, 1, 2, 1)
    assert m["rappel"] == pytest.approx(2 / 3) and m["precision"] == pytest.approx(0.5)
    assert m["f1"] == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))
    assert m["exactitude"] == pytest.approx(0.5)
    assert m["taux_faux_negatifs"] == pytest.approx(1 / 3)
    assert m["rappel"] + m["taux_faux_negatifs"] == pytest.approx(1.0)


@pytest.mark.exigence("EX04")
def test_entrainement_produit_un_modele_conforme_au_contrat():
    pipeline = entrainer(ENTRAINEMENT.head(2000))
    assert list(pipeline.classes_) == [0, 1] and pipeline.n_features_in_ == 6
    p = probabilites_defaut(pipeline, EVALUATION)
    assert p.shape == (len(EVALUATION),) and np.all((p >= 0) & (p <= 1)) and np.all(np.isfinite(p))
    with pytest.raises(ValueError, match="inconnu"):
        entrainer(ENTRAINEMENT.head(100), algorithme="foret_magique")


def test_domaine_d_entrainement():
    domaine = domaine_entrainement(ENTRAINEMENT)
    assert set(domaine) == {*d.COLONNES_ENTREE, "taux_effort"}
    assert all(b["min"] <= b["max"] for b in domaine.values())
    assert domaine["age"] == {"min": 18.0, "max": 70.0}


@pytest.mark.exigence("EX14", "EX13")
def test_modele_sauvegarde_est_recharge_et_verifie_par_le_service(tmp_path):
    pipeline = entrainer(ENTRAINEMENT.head(3000))
    mesures = metriques(EVALUATION[d.CIBLE], probabilites_defaut(pipeline, EVALUATION))
    meta = sauvegarder_modele(
        pipeline, ENTRAINEMENT.head(3000), mesures, tmp_path, "9.9.9", nom="essai"
    )
    fichier = tmp_path / "essai_v9.9.9.joblib"
    assert meta["empreinte_sha256"] == calculer_empreinte(fichier)
    assert (
        json.loads((tmp_path / "essai_v9.9.9.json").read_text(encoding="utf-8"))["version"]
        == "9.9.9"
    )
    service = ServicePrediction(fichier, tmp_path / "essai_v9.9.9.json")
    service.charger()
    assert service.metadonnees["donnees"]["type"] == "synthetique"
    assert "performance réelle" in service.metadonnees["donnees"]["avertissement"]


def test_audit_segments_coherent_avec_les_metriques_globales():
    pipeline = entrainer(ENTRAINEMENT)
    p = probabilites_defaut(pipeline, EVALUATION)
    audit = audit_segments(EVALUATION, p).set_index("segment")
    globale = metriques(EVALUATION[d.CIBLE], p)
    assert audit.loc["Ensemble", "n"] == len(EVALUATION)
    assert audit.loc["Ensemble", "rappel"] == pytest.approx(globale["rappel"])
    familles = audit.loc[["18-24 ans", "25-34 ans", "35-49 ans", "50 ans et +"], "n"]
    assert familles.sum() == len(EVALUATION), "les tranches d'âge partitionnent la population"


def test_audit_detecte_le_segment_a_faux_negatifs_eleves():
    """Preuve de l'écart entre performance globale et performance par profil (voir rapport)."""
    pipeline = entrainer(ENTRAINEMENT)
    audit = audit_segments(EVALUATION, probabilites_defaut(pipeline, EVALUATION)).set_index(
        "segment"
    )
    segment = audit.loc["< 2 ans & >= 24 mois"]
    assert segment["defauts"] >= 30, "effectif suffisant pour conclure"
    assert segment["taux_faux_negatifs"] > audit.loc["Ensemble", "taux_faux_negatifs"] + 0.30


@pytest.mark.exigence("EX07")
def test_cas_dores_du_code_identiques_au_fichier_de_reference():
    from ml.cas_dores import construire_cas_dores

    figes = json.loads(
        (config.RACINE / "tests/reference/cas_dores.json").read_text(encoding="utf-8")
    )
    construits = construire_cas_dores()
    assert [(c["id"], c["entree"]) for c in construits] == [(c["id"], c["entree"]) for c in figes]
    for cas in construits:
        valider_demande(cas["entree"])
