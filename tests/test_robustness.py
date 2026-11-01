"""Tests de robustesse : valeurs manquantes, non numériques, non finies, limites, atypiques, schéma."""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from app.preprocessing import construire_caracteristiques
from app.validation import valider_demande
from tests.scenarios import ABSENT, PAYLOAD_VALIDE, avec, brut

CHAMPS = list(PAYLOAD_VALIDE)
JSON = {"Content-Type": "application/json"}


def probabilite_valide(corps: dict) -> None:
    """Test de contrat : la probabilité est finie et appartient à [0 ; 1]."""
    probabilite = corps["probabilite_defaut"]
    assert math.isfinite(probabilite)
    assert 0.0 <= probabilite <= 1.0


def envoyer(client, corps: dict):
    return client.post("/predict", content=brut(corps), headers=JSON)


# --- R1 : valeurs manquantes ------------------------------------------------------------
@pytest.mark.exigence("EX06")
@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("mode", ["absent", "nul"])
def test_valeurs_manquantes(client, champ, mode):
    corps = avec(**{champ: ABSENT if mode == "absent" else None})
    reponse = envoyer(client, corps)
    assert reponse.status_code == 422
    attendu = "champ_manquant" if mode == "absent" else "type_invalide"
    assert any(d["champ"] == champ and d["code"] == attendu for d in reponse.json()["details"])


# --- R2 : valeurs non numériques --------------------------------------------------------
NON_NUMERIQUES = [
    "abc",
    "",
    " ",
    "1e5",
    "٣٥",
    "💰",
    "NaN",
    "Infinity",
    True,
    False,
    [],
    [1],
    {},
    {"a": 1},
]


@pytest.mark.exigence("EX02", "EX08", "EX03", "EX01")
@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("valeur", NON_NUMERIQUES, ids=lambda v: f"{type(v).__name__}-{str(v)[:6]}")
def test_valeurs_non_numeriques(client, champ, valeur):
    reponse = client.post("/predict", json=avec(**{champ: valeur}))
    assert reponse.status_code == 422
    assert any(
        d["champ"] == champ and d["code"] == "type_invalide" for d in reponse.json()["details"]
    )


# --- R3 : valeurs infinies ou non finies ------------------------------------------------
@pytest.mark.exigence("EX02", "EX10")
@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("jeton", ["NaN", "Infinity", "-Infinity"])
def test_constantes_non_standard_refusees(client, champ, jeton):
    valeurs = {c: json.dumps(v) for c, v in PAYLOAD_VALIDE.items()} | {champ: jeton}
    corps = "{" + ",".join(f'"{c}":{v}' for c, v in valeurs.items()) + "}"
    reponse = client.post("/predict", content=corps.encode(), headers=JSON)
    assert reponse.status_code == 400 and reponse.json()["erreur"] == "json_invalide"


@pytest.mark.exigence("EX02", "EX01", "EX03", "EX08")
@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("litteral", ["1e999", "-1e999"])
def test_infinis_par_debordement_refuses(client, champ, litteral):
    valeurs = {c: json.dumps(v) for c, v in PAYLOAD_VALIDE.items()} | {champ: litteral}
    corps = "{" + ",".join(f'"{c}":{v}' for c, v in valeurs.items()) + "}"
    reponse = client.post("/predict", content=corps.encode(), headers=JSON)
    assert reponse.status_code == 422
    assert any(
        d["champ"] == champ and d["code"] == "valeur_non_finie" for d in reponse.json()["details"]
    )


@pytest.mark.exigence("EX10")
@pytest.mark.parametrize(
    "octets", [b"\xff\xff\xff", b'{"age": "\xff"}', b"\x00\x01\x02", '{"age": 35}'.encode("utf-16")]
)
def test_octets_invalides_refuses(client, octets):
    reponse = client.post("/predict", content=octets, headers=JSON)
    assert reponse.status_code in (400, 422) and "erreur" in reponse.json()


# --- R4 : valeurs aux limites des intervalles -------------------------------------------
LIMITES = [
    # (champ, accepté bas, accepté haut, refusé bas, refusé haut, modifs. de cohérence pour le haut)
    ("age", 18, 75, 17, 76, {"anciennete_activite": 0}),
    ("revenu_mensuel", 1, 20_000_000, 0, 20_000_001, {}),
    ("montant_credit", 1, 200_000_000, 0, 200_000_001, {}),
    ("duree_mois", 1, 120, 0, 121, {}),
    ("anciennete_activite", 0, 59, -0.001, 61, {"age": 75}),
]


@pytest.mark.exigence("EX01", "EX02", "EX03", "EX08", "EX12", "EX04")
@pytest.mark.parametrize(
    ("champ", "bas", "haut", "_ko_bas", "_ko_haut", "contexte"),
    LIMITES,
    ids=[ligne[0] for ligne in LIMITES],
)
def test_limites_incluses_acceptees(client, champ, bas, haut, _ko_bas, _ko_haut, contexte):
    for valeur in (bas, haut):
        reponse = client.post("/predict", json=avec(**{**contexte, champ: valeur}))
        assert reponse.status_code == 200, (champ, valeur, reponse.text)
        probabilite_valide(reponse.json())


@pytest.mark.exigence("EX01", "EX02", "EX03", "EX08", "EX12")
@pytest.mark.parametrize(
    ("champ", "_ok_bas", "_ok_haut", "ko_bas", "ko_haut", "contexte"),
    LIMITES,
    ids=[ligne[0] for ligne in LIMITES],
)
def test_limites_depassees_refusees(client, champ, _ok_bas, _ok_haut, ko_bas, ko_haut, contexte):
    for valeur in (ko_bas, ko_haut):
        reponse = client.post("/predict", json=avec(**{**contexte, champ: valeur}))
        assert reponse.status_code == 422, (champ, valeur, reponse.text)
        assert any(
            d["champ"] == champ and d["code"] == "hors_limites" for d in reponse.json()["details"]
        )


# --- R5 : entrées valides mais très éloignées des données d'entraînement -----------------
ATYPIQUES = [
    ("revenu_20M", {"revenu_mensuel": 20_000_000}, {"revenu_mensuel"}),
    ("revenu_1_FCFA", {"revenu_mensuel": 1}, {"revenu_mensuel", "taux_effort"}),
    (
        "montant_200M",
        {"montant_credit": 200_000_000, "revenu_mensuel": 1_000_000, "duree_mois": 120},
        {"montant_credit", "duree_mois"},
    ),
    ("duree_120", {"duree_mois": 120}, {"duree_mois"}),
    ("age_75", {"age": 75}, {"age"}),
    ("anciennete_59", {"age": 75, "anciennete_activite": 59}, {"age", "anciennete_activite"}),
    (
        "tout_extreme",
        {
            "age": 75,
            "anciennete_activite": 59,
            "revenu_mensuel": 20_000_000,
            "montant_credit": 200_000_000,
            "duree_mois": 120,
        },
        {"age", "anciennete_activite", "revenu_mensuel", "montant_credit", "duree_mois"},
    ),
]


@pytest.mark.exigence("EX15", "EX04")
@pytest.mark.parametrize(
    ("modifs", "champs"), [(m, c) for _, m, c in ATYPIQUES], ids=[nom for nom, _, _ in ATYPIQUES]
)
def test_entrees_atypiques_valides_signalees(client, modifs, champs):
    reponse = client.post("/predict", json=avec(**modifs))
    assert reponse.status_code == 200
    corps = reponse.json()
    probabilite_valide(corps)
    assert champs <= {a["champ"] for a in corps["alertes"]}
    assert {a["code"] for a in corps["alertes"]} == {"hors_domaine_entrainement"}


@pytest.mark.exigence("EX15", "EX02")
def test_distinction_entree_invalide_et_entree_inhabituelle(client):
    """Invalide -> rejetée (422). Inhabituelle mais valide -> traitée avec alerte (200)."""
    invalide = client.post("/predict", json=avec(revenu_mensuel=20_000_001))
    inhabituelle = client.post("/predict", json=avec(revenu_mensuel=20_000_000))
    assert invalide.status_code == 422 and "alertes" not in invalide.json()
    assert inhabituelle.status_code == 200 and inhabituelle.json()["alertes"]


# --- R6 : schéma incorrect ---------------------------------------------------------------
SCHEMAS = {
    "casse_differente": {
        "Age": 35,
        "Revenu_Mensuel": 250000,
        "montant_credit": 1000000,
        "duree_mois": 12,
        "anciennete_activite": 4,
    },
    "imbrique": {"demande": PAYLOAD_VALIDE},
    "lot_de_demandes": [PAYLOAD_VALIDE, PAYLOAD_VALIDE],
    "alias_anglais": {"age": 35, "income": 250000, "amount": 1000000, "months": 12, "seniority": 4},
    "valeurs_dans_des_listes": {k: [v] for k, v in PAYLOAD_VALIDE.items()},
    "champ_supplementaire_imbrique": {**PAYLOAD_VALIDE, "extra": {"a": {"b": 1}}},
    "tableau_vide": [],
    "chaine": "age=35",
}


@pytest.mark.exigence("EX09", "EX06", "EX10")
@pytest.mark.parametrize("corps", SCHEMAS.values(), ids=SCHEMAS.keys())
def test_schema_incorrect_refuse(client, corps):
    reponse = client.post("/predict", json=corps)
    assert reponse.status_code == 422 and reponse.json()["erreur"] == "donnees_invalides"


# --- R7 : déterminisme et propriétés (tests métamorphiques) ------------------------------
@pytest.mark.exigence("EX13")
def test_meme_requete_meme_resultat(client):
    resultats = {
        client.post("/predict", json=PAYLOAD_VALIDE).json()["probabilite_defaut"] for _ in range(20)
    }
    assert len(resultats) == 1


@pytest.mark.exigence("EX13")
def test_ordre_des_cles_et_representation_numerique_sans_effet(client):
    reference = client.post("/predict", json=PAYLOAD_VALIDE).json()["probabilite_defaut"]
    melange = dict(reversed(list(PAYLOAD_VALIDE.items())))
    flottants = {c: float(v) for c, v in PAYLOAD_VALIDE.items()}
    notation_scientifique = b'{"age":3.5e1,"revenu_mensuel":2.5e5,"montant_credit":1e6,"duree_mois":1.2e1,"anciennete_activite":4}'
    for envoi in (
        client.post("/predict", json=melange),
        client.post("/predict", json=flottants),
        client.post("/predict", content=notation_scientifique, headers=JSON),
    ):
        assert envoi.status_code == 200 and envoi.json()["probabilite_defaut"] == reference


@pytest.mark.exigence("EX13")
def test_aucune_fuite_d_etat_entre_requetes(client):
    a, b = (
        PAYLOAD_VALIDE,
        avec(
            age=22,
            revenu_mensuel=90000,
            montant_credit=2_000_000,
            duree_mois=36,
            anciennete_activite=1,
        ),
    )
    p_a = client.post("/predict", json=a).json()["probabilite_defaut"]
    p_b = client.post("/predict", json=b).json()["probabilite_defaut"]
    for _ in range(10):
        assert client.post("/predict", json=b).json()["probabilite_defaut"] == p_b
        assert client.post("/predict", json=a).json()["probabilite_defaut"] == p_a
    assert p_a != p_b


@pytest.mark.exigence("EX13")
def test_requetes_concurrentes_coherentes_avec_le_resultat_sequentiel(client):
    profils = [avec(age=a, duree_mois=d) for a, d in ((25, 6), (35, 12), (45, 24), (60, 48))]
    attendu = [client.post("/predict", json=p).json()["probabilite_defaut"] for p in profils]

    def appeler(i):
        reponse = client.post("/predict", json=profils[i % 4])
        return i % 4, reponse.status_code, reponse.json()["probabilite_defaut"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultats = list(pool.map(appeler, range(200)))
    assert all(statut == 200 and p == attendu[k] for k, statut, p in resultats)


def prob(service, **modifs) -> float:
    return service.predire(construire_caracteristiques(valider_demande(avec(**modifs))))


PROFILS_BASE = [
    {
        "age": 30,
        "revenu_mensuel": 150_000,
        "montant_credit": 900_000,
        "duree_mois": 12,
        "anciennete_activite": 3,
    },
    {
        "age": 45,
        "revenu_mensuel": 400_000,
        "montant_credit": 2_000_000,
        "duree_mois": 24,
        "anciennete_activite": 10,
    },
    {
        "age": 25,
        "revenu_mensuel": 100_000,
        "montant_credit": 800_000,
        "duree_mois": 9,
        "anciennete_activite": 1,
    },
]
GRILLES = {
    "revenu_mensuel": ([60_000 * 1.25**k for k in range(14)], -1),
    "montant_credit": ([100_000 * 1.35**k for k in range(14)], +1),
    "anciennete_activite": ([0, 1, 2, 3, 4, 6, 8, 10, 14, 20], -1),
    "age": (list(range(20, 70, 5)), -1),
}


@pytest.mark.exigence("EX13", "EX04")
@pytest.mark.parametrize("champ", GRILLES)
@pytest.mark.parametrize("profil", range(len(PROFILS_BASE)))
def test_monotonie_metier_dans_le_domaine_d_entrainement(service, champ, profil):
    """Plus de revenu, d'ancienneté ou d'âge -> risque non croissant ; plus de montant -> non décroissant."""
    valeurs, sens = GRILLES[champ]
    contexte = {"age": {"anciennete_activite": 0}, "anciennete_activite": {"age": 60}}.get(
        champ, {}
    )
    probabilites = [
        prob(service, **{**PROFILS_BASE[profil], **contexte, champ: v}) for v in valeurs
    ]
    differences = np.diff(probabilites) * sens
    assert np.all(differences >= -1e-12), (champ, probabilites)


# --- R8 : fuzzing reproductible ---------------------------------------------------------
POOL = [
    None,
    True,
    False,
    "",
    "abc",
    "35",
    [],
    [1],
    {},
    {"a": 1},
    0,
    -0.0,
    1,
    -1,
    17,
    18,
    75,
    76,
    3.14,
    1e308,
    -1e308,
    5e-324,
    2**53,
    2**63,
    2**64,
    10**30,
    10**400,
    float("nan"),
    float("inf"),
    -float("inf"),
    0.1 + 0.2,
    "\u0000",
    "💥",
]


def cas_fuzz(rng: np.random.Generator) -> dict:
    corps = dict(PAYLOAD_VALIDE)
    for champ in CHAMPS:
        if rng.random() < 0.45:
            corps[champ] = POOL[rng.integers(len(POOL))]
    if rng.random() < 0.10:
        corps.pop(CHAMPS[rng.integers(len(CHAMPS))])
    if rng.random() < 0.10:
        corps[f"cle_{rng.integers(1000)}"] = POOL[rng.integers(len(POOL))]
    return corps


@pytest.mark.exigence("EX10", "EX02", "EX04", "EX11")
def test_fuzzing_aucune_erreur_serveur(client):
    """800 requêtes pseudo-aléatoires (graine fixe) : jamais de 5xx, toujours du JSON structuré."""
    rng = np.random.default_rng(2026)
    statuts = {200: 0, 400: 0, 422: 0}
    for _ in range(800):
        reponse = envoyer(client, cas_fuzz(rng))
        assert reponse.status_code in statuts, reponse.text[:200]
        statuts[reponse.status_code] += 1
        corps = reponse.json()
        assert "id_requete" in corps
        if reponse.status_code == 200:
            probabilite_valide(corps)
    assert statuts[200] > 10 and statuts[422] > 100, statuts
