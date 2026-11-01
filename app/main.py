"""API de prédiction du risque de crédit (v0.1 - premier jet)."""

from __future__ import annotations

import logging
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import config, prediction, preprocessing, validation

journal = logging.getLogger("credit_risk.api")


def create_app(service=None):
    api = FastAPI(title="API de risque de crédit (prototype)", version=config.VERSION_APPLICATION)
    api.state.service = service or prediction.ServicePrediction()
    try:
        api.state.service.charger()
    except Exception:
        journal.warning("Modèle non chargé au démarrage")

    @api.middleware("http")
    async def identifiant(request: Request, call_next):
        id_requete = uuid.uuid4().hex[:16]
        request.state.id_requete = id_requete
        reponse = await call_next(request)
        reponse.headers["X-Request-ID"] = id_requete
        return reponse

    @api.get("/health")
    def health(request: Request):
        service = request.app.state.service
        return {
            "statut": "ok",
            "modele_charge": service.est_charge,
            "version_application": config.VERSION_APPLICATION,
        }

    @api.get("/model-info")
    def model_info(request: Request):
        service = request.app.state.service
        service.assurer_disponible()
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
            "chemin_modele": str(service.chemin_modele),
        }

    @api.post("/predict")
    async def predict(request: Request):
        id_requete = request.state.id_requete
        try:
            payload = await request.json()
            demande = validation.valider_demande(payload)
            caracteristiques = preprocessing.construire_caracteristiques(demande)
            probabilite = request.app.state.service.predire(caracteristiques)
            interpretation = prediction.interpreter_probabilite(probabilite)
            return {
                "probabilite_defaut": round(probabilite, 6),
                "niveau_risque": interpretation.niveau,
                "recommandation": interpretation.recommandation,
                "alertes": validation.evaluer_alertes(demande, {}),
                "version_modele": "1.0",
                "id_requete": id_requete,
            }
        except validation.ErreurValidation as exc:
            return JSONResponse(
                status_code=422,
                content={
                    "erreur": "donnees_invalides",
                    "message": "Les données de la demande sont invalides.",
                    "id_requete": id_requete,
                    "details": [detail.en_dict() for detail in exc.details],
                },
            )
        except Exception as exc:
            journal.exception("Erreur pendant la prédiction")
            return JSONResponse(
                status_code=500,
                content={
                    "erreur": "erreur_interne",
                    "message": str(exc),
                    "trace": traceback.format_exc(),
                    "id_requete": id_requete,
                },
            )

    return api


app = create_app()
