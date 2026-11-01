"""API de prédiction du risque de crédit (FastAPI).

Contrat d'erreur uniforme : {"erreur": <code>, "message": <texte>, "id_requete": <id>[, "details": [...]]}
Les erreurs internes ne divulguent jamais de trace, de chemin ni de message d'exception :
le détail technique est écrit dans le journal serveur, corrélé par `id_requete`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config, prediction, preprocessing, validation

journal = logging.getLogger("credit_risk.api")

MESSAGE_INTERNE = (
    "Une erreur interne est survenue. Veuillez réessayer ou contacter l'administrateur "
    "en indiquant l'identifiant de requête."
)
MESSAGE_MODELE = "Le modèle de prédiction est momentanément indisponible."


def _erreur(
    statut: int,
    code: str,
    message: str,
    id_requete: str | None,
    details: list[dict] | None = None,
    entetes: dict[str, str] | None = None,
) -> JSONResponse:
    corps: dict[str, Any] = {"erreur": code, "message": message, "id_requete": id_requete}
    if details:
        corps["details"] = details
    return JSONResponse(status_code=statut, content=corps, headers=entetes)


def _refuser_constante(nom: str):
    """NaN, Infinity et -Infinity ne font pas partie du JSON standard (RFC 8259)."""
    raise ValueError(f"constante JSON non standard : {nom}")


def _objet_sans_doublon(paires: list[tuple[str, Any]]) -> dict[str, Any]:
    """Une clé dupliquée rend la requête ambiguë (la dernière valeur l'emporterait en silence)."""
    objet: dict[str, Any] = {}
    for cle, valeur in paires:
        if cle in objet:
            raise ValueError("clé dupliquée")
        objet[cle] = valeur
    return objet


def _schema_demande() -> dict:
    proprietes = {
        champ: {
            "type": "integer" if limite.entier else "number",
            "minimum": limite.minimum,
            "maximum": limite.maximum,
            "description": f"Unité : {limite.unite}",
        }
        for champ, limite in config.LIMITES.items()
    }
    return {
        "type": "object",
        "required": list(config.LIMITES),
        "properties": proprietes,
        "additionalProperties": False,
    }


REPONSES_DOCUMENTEES = {
    200: {"description": "Probabilité de défaut et niveau de risque."},
    400: {"description": "JSON mal formé."},
    413: {"description": "Corps de requête trop volumineux."},
    415: {"description": "Content-Type différent de application/json."},
    422: {"description": "Données invalides (détails par champ)."},
    500: {"description": "Erreur interne (message générique, aucun détail technique)."},
    503: {"description": "Modèle indisponible."},
}


def create_app(service: prediction.ServicePrediction | None = None) -> FastAPI:
    """Fabrique l'application ; `service` permet d'injecter un service (tests)."""
    api = FastAPI(
        title="API de risque de crédit (prototype)",
        version=config.VERSION_APPLICATION,
        description="Estimation de la probabilité de défaut de remboursement. "
        "Données d'entraînement synthétiques : usage de test uniquement.",
    )
    api.state.service = service or prediction.ServicePrediction()
    try:
        api.state.service.charger()
    except prediction.ModeleIndisponible:
        journal.error("Démarrage sans modèle : les prochaines requêtes retenteront le chargement")

    @api.middleware("http")
    async def identifiant_et_filet_de_securite(request: Request, call_next):
        id_requete = uuid.uuid4().hex[:16]
        request.state.id_requete = id_requete
        debut = time.perf_counter()
        try:
            reponse = await call_next(request)
        except Exception:
            journal.exception(
                "Erreur non gérée id=%s %s %s", id_requete, request.method, request.url.path
            )
            reponse = _erreur(500, "erreur_interne", MESSAGE_INTERNE, id_requete)
        reponse.headers["X-Request-ID"] = id_requete
        journal.info(
            "id=%s %s %s -> %s en %.1f ms",
            id_requete,
            request.method,
            request.url.path,
            reponse.status_code,
            (time.perf_counter() - debut) * 1000,
        )
        return reponse

    @api.exception_handler(StarletteHTTPException)
    async def erreur_http(request: Request, exc: StarletteHTTPException):
        codes = {
            404: ("ressource_introuvable", "La ressource demandée n'existe pas."),
            405: ("methode_non_autorisee", "Méthode HTTP non autorisée pour cette ressource."),
        }
        code, message = codes.get(exc.status_code, ("erreur_http", "Requête non traitée."))
        return _erreur(
            exc.status_code,
            code,
            message,
            getattr(request.state, "id_requete", None),
            entetes=dict(exc.headers) if exc.headers else None,
        )

    def _modele_indisponible(id_requete: str) -> JSONResponse:
        return _erreur(
            503, "modele_indisponible", MESSAGE_MODELE, id_requete, entetes={"Retry-After": "30"}
        )

    @api.get("/health")
    def health(request: Request):
        """Disponibilité du service : 200 si le modèle est chargé, 503 sinon."""
        try:
            request.app.state.service.assurer_disponible()
            disponible = True
        except prediction.ModeleIndisponible:
            disponible = False
        corps = {
            "statut": "ok" if disponible else "indisponible",
            "modele_charge": disponible,
            "version_application": config.VERSION_APPLICATION,
        }
        return JSONResponse(corps, status_code=200 if disponible else 503)

    @api.get("/model-info")
    def model_info(request: Request):
        """Métadonnées publiques de la version du modèle."""
        service = request.app.state.service
        try:
            service.assurer_disponible()
        except prediction.ModeleIndisponible:
            return _modele_indisponible(request.state.id_requete)
        meta = service.metadonnees
        return {
            "nom": meta["nom"],
            "version": meta["version"],
            "algorithme": meta["algorithme"],
            "date_entrainement": meta.get("date_entrainement"),
            "variables": meta["variables"],
            "nb_variables": len(meta["variables"]),
            "empreinte_sha256": meta["empreinte_sha256"],
            "metriques_reference": meta.get("metriques_reference"),
            "donnees": meta.get("donnees"),
            "seuils_risque": {
                "modere": config.SEUIL_RISQUE_MODERE,
                "eleve": config.SEUIL_RISQUE_ELEVE,
            },
            "version_application": config.VERSION_APPLICATION,
        }

    @api.post(
        "/predict",
        responses=REPONSES_DOCUMENTEES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _schema_demande()}},
            }
        },
    )
    async def predict(request: Request):
        """Estime la probabilité de défaut d'un demandeur de crédit."""
        id_requete = request.state.id_requete
        service = request.app.state.service

        type_contenu = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if type_contenu != "application/json":
            return _erreur(
                415,
                "type_contenu_non_supporte",
                "Le Content-Type doit être application/json.",
                id_requete,
            )
        try:
            taille_annoncee = int(request.headers.get("content-length", "0"))
        except ValueError:
            taille_annoncee = 0
        corps = b"" if taille_annoncee > config.TAILLE_MAX_CORPS else await request.body()
        if taille_annoncee > config.TAILLE_MAX_CORPS or len(corps) > config.TAILLE_MAX_CORPS:
            return _erreur(
                413,
                "corps_trop_volumineux",
                f"Le corps de la requête dépasse {config.TAILLE_MAX_CORPS} octets.",
                id_requete,
            )
        try:
            payload = json.loads(
                corps, parse_constant=_refuser_constante, object_pairs_hook=_objet_sans_doublon
            )
        except (ValueError, RecursionError):
            return _erreur(
                400, "json_invalide", "Le corps de la requête n'est pas un JSON valide.", id_requete
            )

        try:
            demande = validation.valider_demande(payload)
        except validation.ErreurValidation as exc:
            return _erreur(
                422,
                "donnees_invalides",
                "Les données de la demande sont invalides.",
                id_requete,
                details=[detail.en_dict() for detail in exc.details],
            )

        try:
            service.assurer_disponible()
            caracteristiques = preprocessing.construire_caracteristiques(demande)
            probabilite = service.predire(caracteristiques)
            interpretation = prediction.interpreter_probabilite(probabilite)
            alertes = validation.evaluer_alertes(demande, service.domaine_entrainement)
            version_modele = service.metadonnees["version"]
        except prediction.ModeleIndisponible:
            return _modele_indisponible(id_requete)
        except preprocessing.ErreurPretraitement:
            journal.exception("Échec du prétraitement id=%s", id_requete)
            return _erreur(500, "erreur_pretraitement", MESSAGE_INTERNE, id_requete)
        except prediction.ErreurPrediction as exc:
            journal.exception("Échec de la prédiction id=%s", id_requete)
            return _erreur(500, exc.code, MESSAGE_INTERNE, id_requete)

        return {
            "probabilite_defaut": round(probabilite, 6),
            "niveau_risque": interpretation.niveau,
            "recommandation": interpretation.recommandation,
            "alertes": alertes,
            "version_modele": version_modele,
            "id_requete": id_requete,
        }

    return api


app = create_app()
