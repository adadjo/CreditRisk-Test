"""Scénarios fonctionnels de l'API : source unique pour les tests et pour le tableau des résultats.

Chaque scénario précise la requête, le code HTTP attendu, le contenu de la réponse et le
comportement attendu de l'application. `executer_scenario` rejoue un scénario et renvoie
le résultat observé (utilisé par pytest et par scripts/executer_scenarios.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PAYLOAD_VALIDE = {
    "age": 35,
    "revenu_mensuel": 250000,
    "montant_credit": 1000000,
    "duree_mois": 12,
    "anciennete_activite": 4,
}
ABSENT = object()  # valeur spéciale : retire le champ de la requête


def avec(**modifications: Any) -> dict:
    """Copie de la requête valide avec modifications ; `ABSENT` supprime le champ."""
    corps = dict(PAYLOAD_VALIDE)
    for cle, valeur in modifications.items():
        if valeur is ABSENT:
            corps.pop(cle, None)
        else:
            corps[cle] = valeur
    return corps


def brut(corps: dict) -> bytes:
    """Sérialisation JSON autorisant les constantes non standard (NaN, Infinity)."""
    return json.dumps(corps, allow_nan=True).encode()


JSON_ENTETE = {"Content-Type": "application/json"}


@dataclass(frozen=True)
class ScenarioApi:
    id: str
    titre: str
    exigences: tuple[str, ...]
    methode: str = "POST"
    chemin: str = "/predict"
    json: Any = ABSENT
    contenu: bytes | None = None
    entetes: dict[str, str] = field(default_factory=dict)
    service: str = "normal"  # "normal" ou "sans_modele"
    statut_attendu: int = 200
    code_erreur: str | None = None
    details: tuple[tuple[str, str], ...] = ()
    contenu_attendu: str = ""
    comportement: str = ""


SCENARIOS_API: tuple[ScenarioApi, ...] = (
    ScenarioApi(
        "S01",
        "Requête valide",
        ("EX04", "EX16"),
        json=PAYLOAD_VALIDE,
        contenu_attendu="probabilite_defaut dans [0 ; 1], niveau_risque, recommandation, alertes, version_modele",
        comportement="Pipeline complet exécuté, aucune erreur.",
    ),
    ScenarioApi(
        "S02",
        "Champ obligatoire absent (revenu_mensuel)",
        ("EX06",),
        json=avec(revenu_mensuel=ABSENT),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("revenu_mensuel", "champ_manquant"),),
        contenu_attendu="Erreur structurée désignant le champ manquant",
        comportement="Requête rejetée avant tout appel au modèle.",
    ),
    ScenarioApi(
        "S03",
        "Âge négatif",
        ("EX01",),
        json=avec(age=-5),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("age", "hors_limites"),),
        contenu_attendu="Détail age / hors_limites avec l'intervalle autorisé",
        comportement="Rejet contrôlé, aucune prédiction.",
    ),
    ScenarioApi(
        "S04",
        "Revenu sous forme de texte non numérique",
        ("EX02",),
        json=avec(revenu_mensuel="deux cent mille"),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("revenu_mensuel", "type_invalide"),),
        contenu_attendu="Détail revenu_mensuel / type_invalide",
        comportement="Aucune conversion implicite ; rejet contrôlé.",
    ),
    ScenarioApi(
        "S05",
        'Revenu sous forme de chaîne numérique ("250000")',
        ("EX02",),
        json=avec(revenu_mensuel="250000"),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("revenu_mensuel", "type_invalide"),),
        contenu_attendu="Détail revenu_mensuel / type_invalide",
        comportement="Le contrat exige un nombre JSON : pas de coercition silencieuse.",
    ),
    ScenarioApi(
        "S06",
        "Montant du crédit nul",
        ("EX08",),
        json=avec(montant_credit=0),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("montant_credit", "hors_limites"),),
        contenu_attendu="Détail montant_credit / hors_limites",
        comportement="Rejet contrôlé (évite log(0) = -infini dans le prétraitement).",
    ),
    ScenarioApi(
        "S07",
        "Montant du crédit négatif",
        ("EX08",),
        json=avec(montant_credit=-1_000_000),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("montant_credit", "hors_limites"),),
        contenu_attendu="Détail montant_credit / hors_limites",
        comportement="Rejet contrôlé.",
    ),
    ScenarioApi(
        "S08",
        "Durée de crédit non entière (12,5 mois)",
        ("EX03",),
        json=avec(duree_mois=12.5),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("duree_mois", "non_entier"),),
        contenu_attendu="Détail duree_mois / non_entier",
        comportement="Pas de troncature silencieuse (12,5 ne devient pas 12).",
    ),
    ScenarioApi(
        "S09",
        "Champ supplémentaire non autorisé (genre)",
        ("EX09",),
        json={**PAYLOAD_VALIDE, "genre": "F"},
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("genre", "champ_non_autorise"),),
        contenu_attendu="Détail genre / champ_non_autorise",
        comportement="Schéma strict : un attribut inattendu n'est jamais ignoré en silence.",
    ),
    ScenarioApi(
        "S10",
        "Valeurs extrêmement élevées sur tous les champs",
        ("EX01", "EX02", "EX03", "EX08"),
        json={
            "age": 1_000_000,
            "revenu_mensuel": 1e15,
            "montant_credit": 1e18,
            "duree_mois": 10**9,
            "anciennete_activite": 1e6,
        },
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(
            ("age", "hors_limites"),
            ("revenu_mensuel", "hors_limites"),
            ("montant_credit", "hors_limites"),
            ("duree_mois", "hors_limites"),
            ("anciennete_activite", "hors_limites"),
        ),
        contenu_attendu="Cinq détails hors_limites",
        comportement="Rejet contrôlé ; aucun dépassement numérique.",
    ),
    ScenarioApi(
        "S11",
        "Modèle indisponible (non chargé)",
        ("EX05",),
        json=PAYLOAD_VALIDE,
        service="sans_modele",
        statut_attendu=503,
        code_erreur="modele_indisponible",
        contenu_attendu="Erreur modele_indisponible, en-tête Retry-After, aucun détail technique",
        comportement="Indisponibilité signalée proprement ; pas de plantage.",
    ),
    ScenarioApi(
        "S12",
        "Requête mal formée (JSON tronqué)",
        ("EX10",),
        contenu=b'{"age": 35, "revenu_mensuel": ',
        entetes=JSON_ENTETE,
        statut_attendu=400,
        code_erreur="json_invalide",
        contenu_attendu="Erreur json_invalide",
        comportement="Rejet 400, aucune trace technique.",
    ),
    ScenarioApi(
        "S13",
        "Corps de requête vide",
        ("EX10",),
        contenu=b"",
        entetes=JSON_ENTETE,
        statut_attendu=400,
        code_erreur="json_invalide",
        contenu_attendu="Erreur json_invalide",
        comportement="Rejet 400.",
    ),
    ScenarioApi(
        "S14",
        "JSON valide mais qui n'est pas un objet (liste)",
        ("EX10", "EX06"),
        json=[35, 250000],
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("corps", "schema_invalide"),),
        contenu_attendu="Détail corps / schema_invalide",
        comportement="Rejet 422 contrôlé.",
    ),
    ScenarioApi(
        "S15",
        "Constante non standard NaN dans le JSON",
        ("EX02", "EX10"),
        contenu=brut(avec(revenu_mensuel=float("nan"))),
        entetes=JSON_ENTETE,
        statut_attendu=400,
        code_erreur="json_invalide",
        contenu_attendu="Erreur json_invalide",
        comportement="NaN n'est pas du JSON (RFC 8259) : rejet 400.",
    ),
    ScenarioApi(
        "S16",
        "Infini obtenu par débordement d'exposant (1e999)",
        ("EX02",),
        contenu=b'{"age":35,"revenu_mensuel":1e999,"montant_credit":1000000,"duree_mois":12,"anciennete_activite":4}',
        entetes=JSON_ENTETE,
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("revenu_mensuel", "valeur_non_finie"),),
        contenu_attendu="Détail revenu_mensuel / valeur_non_finie",
        comportement="Valeur infinie rejetée avant le prétraitement.",
    ),
    ScenarioApi(
        "S17",
        "Content-Type non JSON (text/plain)",
        ("EX10",),
        contenu=brut(PAYLOAD_VALIDE),
        entetes={"Content-Type": "text/plain"},
        statut_attendu=415,
        code_erreur="type_contenu_non_supporte",
        contenu_attendu="Erreur type_contenu_non_supporte",
        comportement="Rejet 415.",
    ),
    ScenarioApi(
        "S18",
        "Corps de requête volumineux (1 Mo)",
        ("EX10",),
        contenu=b'{"age": 35, "x": "' + b"a" * 1_000_000 + b'"}',
        entetes=JSON_ENTETE,
        statut_attendu=413,
        code_erreur="corps_trop_volumineux",
        contenu_attendu="Erreur corps_trop_volumineux",
        comportement="Rejet 413 sans analyse du corps.",
    ),
    ScenarioApi(
        "S19",
        "Objet vide {}",
        ("EX06",),
        json={},
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=tuple((champ, "champ_manquant") for champ in PAYLOAD_VALIDE),
        contenu_attendu="Cinq détails champ_manquant",
        comportement="Rejet 422 listant tous les champs.",
    ),
    ScenarioApi(
        "S20",
        "Booléen à la place de la durée",
        ("EX03",),
        json=avec(duree_mois=True),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("duree_mois", "type_invalide"),),
        contenu_attendu="Détail duree_mois / type_invalide",
        comportement="true n'est pas assimilé à 1 mois.",
    ),
    ScenarioApi(
        "S21",
        "Valeur nulle pour l'âge",
        ("EX06", "EX01"),
        json=avec(age=None),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("age", "type_invalide"),),
        contenu_attendu="Détail age / type_invalide",
        comportement="null refusé.",
    ),
    ScenarioApi(
        "S22",
        "Ancienneté incohérente avec l'âge (20 ans, 15 ans d'activité)",
        ("EX12",),
        json=avec(age=20, anciennete_activite=15),
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("anciennete_activite", "incoherence"),),
        contenu_attendu="Détail anciennete_activite / incoherence",
        comportement="Contrôle de cohérence inter-champs.",
    ),
    ScenarioApi(
        "S23",
        "Méthode non autorisée (GET /predict)",
        ("EX10",),
        methode="GET",
        statut_attendu=405,
        code_erreur="methode_non_autorisee",
        contenu_attendu="Erreur methode_non_autorisee, en-tête Allow",
        comportement="Rejet 405 au format uniforme.",
    ),
    ScenarioApi(
        "S24",
        "Ressource inconnue (GET /inconnu)",
        ("EX10",),
        methode="GET",
        chemin="/inconnu",
        statut_attendu=404,
        code_erreur="ressource_introuvable",
        contenu_attendu="Erreur ressource_introuvable",
        comportement="Rejet 404 au format uniforme.",
    ),
    ScenarioApi(
        "S25",
        "JSON profondément imbriqué (4 900 niveaux, 9,8 Ko)",
        ("EX10",),
        contenu=b"[" * 4_900 + b"]" * 4_900,
        entetes=JSON_ENTETE,
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("corps", "schema_invalide"),),
        contenu_attendu="Détail corps / schema_invalide",
        comportement="Aucune récursion non maîtrisée : JSON valide mais non conforme, rejet 422.",
    ),
    ScenarioApi(
        "S27",
        "Clé dupliquée dans le JSON (age deux fois, 35 puis -1)",
        ("EX09", "EX10"),
        contenu=b'{"age":35,"age":-1,"revenu_mensuel":250000,"montant_credit":1000000,'
        b'"duree_mois":12,"anciennete_activite":4}',
        entetes=JSON_ENTETE,
        statut_attendu=400,
        code_erreur="json_invalide",
        contenu_attendu="Erreur json_invalide",
        comportement="Requête ambiguë refusée : pas de pollution de paramètres.",
    ),
    ScenarioApi(
        "S26",
        "Entier gigantesque (10^400) pour le revenu",
        ("EX02",),
        contenu=b'{"age":35,"revenu_mensuel":1'
        + b"0" * 400
        + b',"montant_credit":1000000,"duree_mois":12,"anciennete_activite":4}',
        entetes=JSON_ENTETE,
        statut_attendu=422,
        code_erreur="donnees_invalides",
        details=(("revenu_mensuel", "hors_limites"),),
        contenu_attendu="Détail revenu_mensuel / hors_limites",
        comportement="Aucune conversion en flottant avant le contrôle des bornes.",
    ),
)


def executer_scenario(scenario: ScenarioApi, clients: dict) -> dict:
    """Rejoue un scénario et renvoie le résultat observé (statut, code d'erreur, détails)."""
    client = clients[scenario.service]
    options: dict[str, Any] = {}
    if scenario.json is not ABSENT:
        options["json"] = scenario.json
    if scenario.contenu is not None:
        options["content"] = scenario.contenu
    if scenario.entetes:
        options["headers"] = scenario.entetes
    reponse = client.request(scenario.methode, scenario.chemin, **options)
    try:
        corps = reponse.json()
    except ValueError:
        corps = {}
    details = tuple(
        (d.get("champ"), d.get("code")) for d in corps.get("details", []) if isinstance(d, dict)
    )
    erreur = corps.get("erreur") if isinstance(corps, dict) else None
    conforme = (
        reponse.status_code == scenario.statut_attendu
        and erreur == scenario.code_erreur
        and all(detail in details for detail in scenario.details)
    )
    return {
        "id": scenario.id,
        "statut_observe": reponse.status_code,
        "erreur_observee": erreur,
        "details_observes": details,
        "corps": corps,
        "texte": reponse.text,
        "en_tetes": dict(reponse.headers),
        "conforme": conforme,
    }
