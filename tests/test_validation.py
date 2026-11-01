"""Tests unitaires : validation, prétraitement et interprétation de la probabilité."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app import config
from app.prediction import interpreter_probabilite
from app.preprocessing import (
    VARIABLES_MODELE,
    ErreurPretraitement,
    construire_caracteristiques,
    construire_matrice,
)
from app.validation import DemandeCredit, ErreurValidation, evaluer_alertes, valider_demande
from tests.scenarios import ABSENT, PAYLOAD_VALIDE, avec

NAN, INF = float("nan"), float("inf")


def refus(**modifications) -> set[tuple[str, str]]:
    """Valide une demande modifiée ; renvoie l'ensemble {(champ, code)} des anomalies."""
    with pytest.raises(ErreurValidation) as info:
        valider_demande(avec(**modifications))
    return {(d.champ, d.code) for d in info.value.details}


@pytest.mark.exigence("EX01", "EX02", "EX03", "EX08")
def test_demande_valide_est_normalisee():
    demande = valider_demande(PAYLOAD_VALIDE)
    assert demande == DemandeCredit(35, 250000.0, 1000000.0, 12, 4.0)
    assert isinstance(demande.age, int) and isinstance(demande.duree_mois, int)
    assert isinstance(demande.revenu_mensuel, float)


# --- EX01 : âge -------------------------------------------------------------------------
@pytest.mark.exigence("EX01")
@pytest.mark.parametrize(
    ("age", "attendu"),
    [(18, 18), (75, 75), (35, 35), (35.0, 35), (30, 30)],
    ids=["min", "max", "typique", "flottant_entier", "trente"],
)
def test_age_accepte(age, attendu):
    anciennete = 0 if age < 20 else 4
    demande = valider_demande(avec(age=age, anciennete_activite=anciennete))
    assert demande.age == attendu and isinstance(demande.age, int)


@pytest.mark.exigence("EX01")
@pytest.mark.parametrize("age", [17, 76, 0, -5, -1, 150, 10**6, 10**400])
def test_age_hors_limites_refuse(age):
    assert ("age", "hors_limites") in refus(age=age)


@pytest.mark.exigence("EX01")
@pytest.mark.parametrize(
    ("age", "code"),
    [
        ("35", "type_invalide"),
        (None, "type_invalide"),
        (True, "type_invalide"),
        (False, "type_invalide"),
        ([35], "type_invalide"),
        ({"v": 35}, "type_invalide"),
        (35.5, "non_entier"),
        (NAN, "valeur_non_finie"),
        (INF, "valeur_non_finie"),
    ],
    ids=["texte", "nul", "vrai", "faux", "liste", "objet", "decimal", "nan", "infini"],
)
def test_age_type_ou_valeur_invalide(age, code):
    assert ("age", code) in refus(age=age)


# --- EX02 / EX08 : revenu et montant ----------------------------------------------------
@pytest.mark.exigence("EX02", "EX08")
@pytest.mark.parametrize("champ", ["revenu_mensuel", "montant_credit"])
@pytest.mark.parametrize(
    "valeur", [1, 250000, 250000.5, 20_000_000], ids=["min", "typique", "decimal", "max"]
)
def test_montants_valides_acceptes(champ, valeur):
    assert getattr(valider_demande(avec(**{champ: valeur})), champ) == float(valeur)


@pytest.mark.exigence("EX02", "EX08")
@pytest.mark.parametrize("champ", ["revenu_mensuel", "montant_credit"])
@pytest.mark.parametrize("valeur", [0, -1, -250000, 0.5, 200_000_001, 1e15, 1e308, 10**400])
def test_montants_hors_limites_refuses(champ, valeur):
    assert (champ, "hors_limites") in refus(**{champ: valeur})


@pytest.mark.exigence("EX02", "EX08")
@pytest.mark.parametrize("champ", ["revenu_mensuel", "montant_credit"])
@pytest.mark.parametrize(
    "valeur",
    ["250000", "abc", "", None, True, [], {}, "NaN"],
    ids=["chaine_numerique", "texte", "vide", "nul", "booleen", "liste", "objet", "texte_nan"],
)
def test_montants_type_invalide(champ, valeur):
    assert (champ, "type_invalide") in refus(**{champ: valeur})


@pytest.mark.exigence("EX02", "EX08")
@pytest.mark.parametrize("champ", ["revenu_mensuel", "montant_credit"])
@pytest.mark.parametrize("valeur", [NAN, INF, -INF], ids=["nan", "plus_infini", "moins_infini"])
def test_montants_non_finis_refuses(champ, valeur):
    assert (champ, "valeur_non_finie") in refus(**{champ: valeur})


def test_plafond_revenu_depasse_par_un():
    assert ("revenu_mensuel", "hors_limites") in refus(revenu_mensuel=20_000_001)


# --- EX03 : durée -----------------------------------------------------------------------
@pytest.mark.exigence("EX03")
@pytest.mark.parametrize(
    "duree", [1, 12, 120, 12.0], ids=["min", "typique", "max", "flottant_entier"]
)
def test_duree_valide_acceptee(duree):
    demande = valider_demande(avec(duree_mois=duree))
    assert demande.duree_mois == int(duree) and isinstance(demande.duree_mois, int)


@pytest.mark.exigence("EX03")
@pytest.mark.parametrize(
    ("duree", "code"),
    [
        (0, "hors_limites"),
        (-12, "hors_limites"),
        (121, "hors_limites"),
        (10**9, "hors_limites"),
        (12.5, "non_entier"),
        (0.5, "non_entier"),
        ("12", "type_invalide"),
        (True, "type_invalide"),
        (None, "type_invalide"),
        (NAN, "valeur_non_finie"),
        (INF, "valeur_non_finie"),
    ],
)
def test_duree_invalide_refusee(duree, code):
    assert ("duree_mois", code) in refus(duree_mois=duree)


# --- EX12 : ancienneté et cohérence -----------------------------------------------------
@pytest.mark.exigence("EX12")
@pytest.mark.parametrize(
    ("age", "anciennete"),
    [(20, 4), (18, 2), (18, 0), (75, 59), (35, 4.5), (40, 0.5)],
    ids=["limite_20_4", "limite_18_2", "zero", "limite_75_59", "decimale", "demi_annee"],
)
def test_coherence_acceptee(age, anciennete):
    assert (
        valider_demande(avec(age=age, anciennete_activite=anciennete)).anciennete_activite
        == anciennete
    )


@pytest.mark.exigence("EX12")
@pytest.mark.parametrize(
    ("age", "anciennete"),
    [(20, 4.5), (18, 2.5), (20, 15), (75, 60)],
    ids=["depasse_de_demi_an", "18_ans_2_5", "20_ans_15", "75_ans_60"],
)
def test_incoherence_age_anciennete_refusee(age, anciennete):
    assert ("anciennete_activite", "incoherence") in refus(age=age, anciennete_activite=anciennete)


@pytest.mark.exigence("EX12")
@pytest.mark.parametrize(
    ("anciennete", "code"),
    [
        (-1, "hors_limites"),
        (61, "hors_limites"),
        ("4", "type_invalide"),
        (NAN, "valeur_non_finie"),
        (None, "type_invalide"),
    ],
)
def test_anciennete_invalide(anciennete, code):
    assert ("anciennete_activite", code) in refus(anciennete_activite=anciennete)


# --- EX06 / EX09 : schéma ---------------------------------------------------------------
@pytest.mark.exigence("EX06")
@pytest.mark.parametrize("champ", list(PAYLOAD_VALIDE))
def test_champ_obligatoire_absent(champ):
    assert refus(**{champ: ABSENT}) == {(champ, "champ_manquant")}


@pytest.mark.exigence("EX06")
def test_objet_vide_liste_tous_les_champs_manquants():
    with pytest.raises(ErreurValidation) as info:
        valider_demande({})
    assert {d.champ for d in info.value.details} == set(PAYLOAD_VALIDE)
    assert {d.code for d in info.value.details} == {"champ_manquant"}


@pytest.mark.exigence("EX06", "EX10")
@pytest.mark.parametrize(
    "corps",
    [None, [], [PAYLOAD_VALIDE], "texte", 42, 3.14, True],
    ids=["nul", "liste_vide", "liste", "texte", "entier", "decimal", "booleen"],
)
def test_corps_non_objet_refuse(corps):
    with pytest.raises(ErreurValidation) as info:
        valider_demande(corps)
    assert [(d.champ, d.code) for d in info.value.details] == [("corps", "schema_invalide")]


@pytest.mark.exigence("EX09")
def test_champs_supplementaires_refuses_et_tries():
    with pytest.raises(ErreurValidation) as info:
        valider_demande({**PAYLOAD_VALIDE, "religion": "x", "genre": "F"})
    assert [(d.champ, d.code) for d in info.value.details] == [
        ("genre", "champ_non_autorise"),
        ("religion", "champ_non_autorise"),
    ]


@pytest.mark.exigence("EX09")
@pytest.mark.parametrize("cle", ["Age", "AGE", " age", "revenu", "salaire", "age​"])
def test_cles_proches_ou_en_majuscules_refusees(cle):
    corps = avec(age=ABSENT)
    corps[cle] = 35
    with pytest.raises(ErreurValidation) as info:
        valider_demande(corps)
    codes = {d.code for d in info.value.details}
    assert {"champ_manquant", "champ_non_autorise"} <= codes


@pytest.mark.exigence("EX09", "EX11")
def test_nom_de_champ_inconnu_tronque():
    with pytest.raises(ErreurValidation) as info:
        valider_demande({**PAYLOAD_VALIDE, "x" * 5000: 1})
    assert len(info.value.details[0].champ) == 64


@pytest.mark.exigence("EX06", "EX11")
def test_anomalies_cumulees_et_valeur_recue_jamais_reproduite():
    hostile = "<script>alert('secret-1234')</script>"
    with pytest.raises(ErreurValidation) as info:
        valider_demande(avec(age=-5, revenu_mensuel=hostile, montant_credit=0, duree_mois=12.5))
    champs = {d.champ for d in info.value.details}
    assert {"age", "revenu_mensuel", "montant_credit", "duree_mois"} <= champs
    texte = " ".join(d.message for d in info.value.details)
    assert "secret-1234" not in texte and "<script>" not in texte


# --- EX15 : alertes hors domaine --------------------------------------------------------
DOMAINE = {
    "age": {"min": 18.0, "max": 70.0},
    "revenu_mensuel": {"min": 40_000.0, "max": 1_500_000.0},
    "montant_credit": {"min": 50_000.0, "max": 14_000_000.0},
    "duree_mois": {"min": 6.0, "max": 48.0},
    "anciennete_activite": {"min": 0.0, "max": 26.0},
    "taux_effort": {"min": 0.02, "max": 5.0},
}


@pytest.mark.exigence("EX15")
def test_aucune_alerte_dans_le_domaine():
    assert evaluer_alertes(valider_demande(PAYLOAD_VALIDE), DOMAINE) == []


@pytest.mark.exigence("EX15")
@pytest.mark.parametrize(
    ("modifs", "champ"),
    [
        ({"revenu_mensuel": 15_000_000}, "revenu_mensuel"),
        ({"revenu_mensuel": 20_000}, "revenu_mensuel"),
        ({"montant_credit": 150_000_000}, "montant_credit"),
        ({"duree_mois": 120}, "duree_mois"),
        ({"duree_mois": 1}, "duree_mois"),
        ({"age": 75}, "age"),
    ],
)
def test_alerte_hors_domaine(modifs, champ):
    alertes = evaluer_alertes(valider_demande(avec(**modifs)), DOMAINE)
    assert champ in {a["champ"] for a in alertes}
    assert {a["code"] for a in alertes} == {"hors_domaine_entrainement"}


@pytest.mark.exigence("EX15")
@pytest.mark.parametrize("age", [18, 70])
def test_bornes_du_domaine_sans_alerte(age):
    assert evaluer_alertes(valider_demande(avec(age=age, anciennete_activite=0)), DOMAINE) == []


@pytest.mark.exigence("EX15")
def test_alerte_sur_taux_d_effort_aberrant():
    demande = valider_demande(avec(revenu_mensuel=100_000, montant_credit=10_000_000, duree_mois=6))
    assert "taux_effort" in {a["champ"] for a in evaluer_alertes(demande, DOMAINE)}


@pytest.mark.exigence("EX15")
def test_champ_absent_du_domaine_ignore():
    assert evaluer_alertes(valider_demande(avec(age=75)), {}) == []


# --- Prétraitement ---------------------------------------------------------------------
@pytest.mark.exigence("EX04", "EX13")
def test_caracteristiques_calculees_et_ordonnees():
    x = construire_caracteristiques(valider_demande(PAYLOAD_VALIDE))
    assert x.shape == (1, len(VARIABLES_MODELE)) == (1, 6)
    attendu = [35, np.log(250000), np.log(1000000), 12, 4, (1_000_000 / 12) / 250_000]
    assert np.allclose(x[0], attendu, rtol=0, atol=1e-12)
    assert x[0, VARIABLES_MODELE.index("taux_effort")] == pytest.approx(1 / 3)


@pytest.mark.exigence("EX13")
def test_transformation_unitaire_identique_a_la_transformation_par_lot():
    lot = construire_matrice([35, 40], [250000, 90000], [1e6, 5e6], [12, 24], [4, 10])
    seul = construire_caracteristiques(valider_demande(PAYLOAD_VALIDE))
    assert np.array_equal(lot[:1], seul) and lot.shape == (2, 6)


@pytest.mark.exigence("EX02", "EX08")
@pytest.mark.parametrize(
    "colonnes",
    [
        ([35], [0], [1e6], [12], [4]),
        ([35], [250000], [-5], [12], [4]),
        ([35], [250000], [0], [12], [4]),
        ([35], [250000], [1e6], [0], [4]),
        ([35], [NAN], [1e6], [12], [4]),
        ([35], [INF], [1e6], [12], [4]),
        (["x"], [250000], [1e6], [12], [4]),
        ([35, 36], [250000], [1e6], [12], [4]),
        ([35], [10**400], [1e6], [12], [4]),
    ],
    ids=[
        "revenu_nul",
        "montant_negatif",
        "montant_nul",
        "duree_nulle",
        "nan",
        "infini",
        "texte",
        "longueurs_differentes",
        "entier_geant",
    ],
)
def test_pretraitement_refuse_les_entrees_non_transformables(colonnes):
    with pytest.raises(ErreurPretraitement):
        construire_matrice(*colonnes)


@pytest.mark.exigence("EX06", "EX11")
def test_variable_attendue_absente_du_pretraitement():
    incomplete = SimpleNamespace(age=35, revenu_mensuel=1.0, montant_credit=1.0, duree_mois=1)
    with pytest.raises(ErreurPretraitement, match="absente"):
        construire_caracteristiques(incomplete)


# --- EX16 : interprétation --------------------------------------------------------------
@pytest.mark.exigence("EX16")
@pytest.mark.parametrize(
    ("p", "niveau"),
    [
        (0.0, "faible"),
        (0.2999, "faible"),
        (0.30, "modere"),
        (0.3001, "modere"),
        (0.5999, "modere"),
        (0.60, "eleve"),
        (0.6001, "eleve"),
        (1.0, "eleve"),
    ],
)
def test_niveaux_de_risque_aux_bornes(p, niveau):
    assert interpreter_probabilite(p).niveau == niveau


@pytest.mark.exigence("EX16", "EX04")
@pytest.mark.parametrize(
    "p", [-0.0001, 1.0001, float("nan"), float("inf"), -float("inf"), "0.5", None, True]
)
def test_probabilite_invalide_refusee_par_l_interpretation(p):
    with pytest.raises(ValueError, match="hors contrat"):
        interpreter_probabilite(p)


@pytest.mark.exigence("EX16")
def test_seuils_de_configuration_coherents():
    assert 0 < config.SEUIL_RISQUE_MODERE < config.SEUIL_RISQUE_ELEVE < 1
