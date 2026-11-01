"""Tests d'intégration : collaboration validation -> prétraitement -> modèle -> API, et pannes injectées."""

from __future__ import annotations

import json
import os
import shutil
from types import SimpleNamespace

import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from app import config, prediction, preprocessing, validation
from app.prediction import (
    ErreurDimensions,
    ModeleIndisponible,
    ServicePrediction,
    calculer_empreinte,
)
from app.preprocessing import VARIABLES_MODELE, ErreurPretraitement
from tests.scenarios import PAYLOAD_VALIDE

MOTS_INTERDITS = (
    "secret",
    "Traceback",
    "RuntimeError",
    "ValueError",
    "/srv",
    ".py",
    'File "',
    "sklearn",
)


def aucune_fuite(reponse) -> None:
    for mot in MOTS_INTERDITS:
        assert mot not in reponse.text, f"fuite d'information : {mot!r} dans {reponse.text[:200]}"


class FauxModele:
    """Modèle simulé : renvoie une probabilité imposée ou lève l'erreur demandée."""

    classes_ = np.array([0, 1])
    n_features_in_ = 6

    def __init__(self, probabilite=0.4, erreur: Exception | None = None):
        self.probabilite, self.erreur = probabilite, erreur

    def predict_proba(self, x):
        if self.erreur is not None:
            raise self.erreur
        return np.array([[1 - self.probabilite, self.probabilite]])


def client_avec_modele(fabrique_client, modele):
    """Client dont le service utilise `modele` (injecté après le chargement initial du vrai modèle)."""
    instance = ServicePrediction()
    instance.charger()
    client = fabrique_client(instance)
    instance._modele = modele
    return client


# --- Scénario principal -----------------------------------------------------------------
@pytest.mark.exigence("EX04", "EX13", "EX14")
def test_pipeline_de_bout_en_bout_et_metadonnees_coherentes(client, service):
    demande = validation.valider_demande(PAYLOAD_VALIDE)  # 1. validation
    x = preprocessing.construire_caracteristiques(demande)  # 2. transformation
    assert x.shape == (1, 6)
    assert x[0, VARIABLES_MODELE.index("taux_effort")] == pytest.approx((1_000_000 / 12) / 250_000)
    p_direct = service.predire(x)  # 3. prédiction

    reponse = client.post("/predict", json=PAYLOAD_VALIDE)  # 4. via l'API
    corps = reponse.json()
    assert reponse.status_code == 200
    assert corps["probabilite_defaut"] == round(p_direct, 6)  # 5. structure et valeur
    assert corps["niveau_risque"] == prediction.interpreter_probabilite(p_direct).niveau

    info = client.get("/model-info").json()  # 6. métadonnées
    fichier = json.loads(config.CHEMIN_METADONNEES.read_text(encoding="utf-8"))
    assert info["version"] == corps["version_modele"] == fichier["version"] == "1.0.0"
    assert info["variables"] == list(VARIABLES_MODELE) == fichier["variables"]
    assert info["empreinte_sha256"] == calculer_empreinte(config.CHEMIN_MODELE)
    assert joblib.load(config.CHEMIN_MODELE).n_features_in_ == info["nb_variables"]


@pytest.mark.exigence("EX14")
def test_modele_versionne_du_depot_conforme_a_la_reference():
    reference = json.loads(
        (config.RACINE / "tests/reference/baseline_v1.0.0.json").read_text(encoding="utf-8")
    )
    assert calculer_empreinte(config.CHEMIN_MODELE) == reference["empreinte_modele_sha256"]


@pytest.mark.exigence("EX04", "EX06")
def test_chaque_module_est_appele_une_fois_dans_l_ordre(client, monkeypatch):
    appels: list[str] = []

    def espionner(objet, nom, etiquette):
        original = getattr(objet, nom)

        def enveloppe(*args, **kwargs):
            appels.append(etiquette)
            return original(*args, **kwargs)

        monkeypatch.setattr(objet, nom, enveloppe)

    espionner(validation, "valider_demande", "validation")
    espionner(preprocessing, "construire_caracteristiques", "pretraitement")
    espionner(ServicePrediction, "predire", "prediction")
    espionner(prediction, "interpreter_probabilite", "interpretation")
    espionner(validation, "evaluer_alertes", "alertes")

    assert client.post("/predict", json=PAYLOAD_VALIDE).status_code == 200
    assert appels == ["validation", "pretraitement", "prediction", "interpretation", "alertes"]

    appels.clear()
    assert client.post("/predict", json={**PAYLOAD_VALIDE, "age": -1}).status_code == 422
    assert appels == ["validation"], "une demande invalide ne doit jamais atteindre le modèle"


# --- Le modèle ne peut pas être chargé --------------------------------------------------
DEFAUTS_MODELE = [
    "fichier_absent",
    "octets_aleatoires",
    "fichier_altere",
    "objet_non_conforme",
    "modele_a_5_variables",
    "metadonnees_incompletes",
    "metadonnees_illisibles",
    "variables_divergentes",
    "metadonnees_absentes",
]


def preparer_modele_defectueux(dossier, defaut):
    modele, meta = dossier / "m.joblib", dossier / "m.json"
    contenu = json.loads(config.CHEMIN_METADONNEES.read_text(encoding="utf-8"))
    shutil.copy(config.CHEMIN_MODELE, modele)
    if defaut == "fichier_absent":
        modele.unlink()
    elif defaut == "octets_aleatoires":
        modele.write_bytes(os.urandom(256))
        contenu["empreinte_sha256"] = calculer_empreinte(modele)
    elif defaut == "fichier_altere":
        octets = bytearray(modele.read_bytes())
        octets[len(octets) // 2] ^= 0xFF
        modele.write_bytes(bytes(octets))
    elif defaut == "objet_non_conforme":
        joblib.dump({"pas": "un modele"}, modele)
        contenu["empreinte_sha256"] = calculer_empreinte(modele)
    elif defaut == "modele_a_5_variables":
        graine = np.random.default_rng(0)
        joblib.dump(LogisticRegression().fit(graine.random((40, 5)), np.tile([0, 1], 20)), modele)
        contenu["empreinte_sha256"] = calculer_empreinte(modele)
    elif defaut == "metadonnees_incompletes":
        del contenu["version"]
    elif defaut == "variables_divergentes":
        contenu["variables"] = list(reversed(contenu["variables"]))
    if defaut == "metadonnees_illisibles":
        meta.write_text("{ceci n'est pas du json", encoding="utf-8")
    elif defaut != "metadonnees_absentes":
        meta.write_text(json.dumps(contenu), encoding="utf-8")
    return modele, meta


@pytest.mark.exigence("EX05", "EX14")
@pytest.mark.parametrize("defaut", DEFAUTS_MODELE)
def test_modele_non_chargeable_est_signale_proprement(
    tmp_path, defaut, fabrique_client, journal_serveur
):
    modele, meta = preparer_modele_defectueux(tmp_path, defaut)
    with pytest.raises(ModeleIndisponible):
        ServicePrediction(modele, meta).charger()
    client = fabrique_client(ServicePrediction(modele, meta))
    for reponse in (
        client.get("/health"),
        client.get("/model-info"),
        client.post("/predict", json=PAYLOAD_VALIDE),
    ):
        assert reponse.status_code == 503
        aucune_fuite(reponse)
    assert client.post("/predict", json=PAYLOAD_VALIDE).json()["erreur"] == "modele_indisponible"
    assert any("Chargement du modèle" in m for m in journal_serveur.messages)


# --- Pannes injectées dans les étages du pipeline ---------------------------------------
@pytest.mark.exigence("EX06", "EX11")
def test_variable_attendue_absente_apres_validation(service, fabrique_client, monkeypatch):
    incomplete = SimpleNamespace(age=35, revenu_mensuel=250000.0, montant_credit=1e6, duree_mois=12)
    monkeypatch.setattr(validation, "valider_demande", lambda _payload: incomplete)
    reponse = fabrique_client(service).post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 500 and reponse.json()["erreur"] == "erreur_pretraitement"
    aucune_fuite(reponse)


@pytest.mark.exigence("EX11")
def test_erreur_de_pretraitement_ne_fuit_pas_et_est_journalisee(
    service, fabrique_client, monkeypatch, journal_serveur
):
    def echec(_demande):
        raise ErreurPretraitement("secret /srv/app/pretraitement.py ligne 42")

    monkeypatch.setattr(preprocessing, "construire_caracteristiques", echec)
    reponse = fabrique_client(service).post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 500 and reponse.json()["erreur"] == "erreur_pretraitement"
    aucune_fuite(reponse)
    journal = journal_serveur.text
    assert "secret /srv/app/pretraitement.py" in journal and "Traceback" in journal
    assert reponse.json()["id_requete"] in journal, "l'identifiant relie la réponse au journal"


@pytest.mark.exigence("EX11")
def test_exception_imprevue_donne_une_erreur_generique(
    service, fabrique_client, monkeypatch, journal_serveur
):
    def panne(_demande):
        raise RuntimeError("secret : connexion /srv/db refusée")

    monkeypatch.setattr(preprocessing, "construire_caracteristiques", panne)
    reponse = fabrique_client(service).post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 500 and reponse.json()["erreur"] == "erreur_interne"
    assert reponse.headers["x-request-id"] == reponse.json()["id_requete"]
    aucune_fuite(reponse)
    assert "secret : connexion /srv/db refusée" in journal_serveur.text


@pytest.mark.exigence("EX04", "EX11")
@pytest.mark.parametrize(
    "forme", [(1, 5), (1, 7), (2, 6), (6,), (1, 6, 1)], ids=lambda f: "x".join(map(str, f))
)
def test_dimensions_incompatibles_avec_le_modele(service, fabrique_client, monkeypatch, forme):
    monkeypatch.setattr(preprocessing, "construire_caracteristiques", lambda _d: np.zeros(forme))
    reponse = fabrique_client(service).post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 500 and reponse.json()["erreur"] == "incoherence_dimensions"
    aucune_fuite(reponse)
    with pytest.raises(ErreurDimensions):
        service.predire(np.zeros(forme))


@pytest.mark.exigence("EX11")
def test_erreur_interne_pendant_la_prediction(fabrique_client, journal_serveur):
    faux = FauxModele(erreur=RuntimeError("secret interne du modèle /srv/m.py"))
    reponse = client_avec_modele(fabrique_client, faux).post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 500 and reponse.json()["erreur"] == "erreur_prediction"
    aucune_fuite(reponse)
    assert "secret interne du modèle" in journal_serveur.text


@pytest.mark.exigence("EX04", "EX11")
@pytest.mark.parametrize(
    "sortie",
    [float("nan"), float("inf"), -0.1, 1.5, 2.0],
    ids=["nan", "infini", "negative", "superieure_a_1", "deux"],
)
def test_probabilite_invalide_du_modele_jamais_transmise(fabrique_client, sortie):
    client = client_avec_modele(fabrique_client, FauxModele(probabilite=sortie))
    reponse = client.post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 500 and reponse.json()["erreur"] == "erreur_prediction"
    assert "probabilite_defaut" not in reponse.json()
    aucune_fuite(reponse)


@pytest.mark.exigence("EX04")
@pytest.mark.parametrize("sortie", [0.0, 1.0], ids=["zero", "un"])
def test_probabilites_extremes_valides_acceptees(fabrique_client, sortie):
    client = client_avec_modele(fabrique_client, FauxModele(probabilite=sortie))
    reponse = client.post("/predict", json=PAYLOAD_VALIDE)
    assert reponse.status_code == 200 and reponse.json()["probabilite_defaut"] == sortie


@pytest.mark.exigence("EX04", "EX11")
def test_entree_non_finie_ou_non_numerique_refusee_par_le_service(service):
    for entree in (np.full((1, 6), np.nan), np.full((1, 6), np.inf)):
        with pytest.raises(prediction.ErreurPrediction):
            service.predire(entree)
    with pytest.raises(prediction.ErreurPrediction):
        service.predire([["a"] * 6])


@pytest.mark.exigence("EX14")
def test_metadonnees_exposees_sans_fuite_de_references_internes(service):
    meta = service.metadonnees
    meta["version"] = "falsifiee"
    assert service.metadonnees["version"] == "1.0.0", "les métadonnées retournées sont une copie"
    assert os.fspath(config.RACINE) not in json.dumps(service.metadonnees)
