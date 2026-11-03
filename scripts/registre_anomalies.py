"""Registre des anomalies : regroupe par cause racine les échecs de la campagne 1 (v0.1).

Chaque test en échec de la campagne 1 est rattaché à UNE seule anomalie (le script refuse de
produire le registre si un échec n'est pas expliqué ou s'il l'est deux fois). Les comptes
(scénarios, tests, injections de pannes, fuzzing) sont lus dans les résultats des campagnes :
rien n'est saisi à la main. Les constats ouverts s'appuient sur l'audit par segment, la
non-régression et la mesure de performance.

Usage : python -m scripts.registre_anomalies
Sorties : reports/registre_anomalies.md et reports/registre_anomalies.json
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
RAPPORTS = RACINE / "reports"

ECHELLE_GRAVITE = {
    "Critique": "résultat invalide ou erroné présenté comme valide, ou modèle non autorisé exécuté, sans aucun signal",
    "Majeure": "erreur serveur sur une entrée du client, divulgation technique, indisponibilité mal signalée ou donnée invalide acceptée",
    "Moyenne": "contrat d'API ou de traçabilité non respecté, sans effet direct sur une décision",
    "Mineure": "écart de forme ou de documentation, sans effet sur le comportement",
}


def _regles(*motifs: str) -> list[str]:
    return list(motifs)


# Un test en échec doit correspondre à exactement une anomalie (par scénario ou par motif).
ANOMALIES: list[dict] = [
    {
        "id": "A-01",
        "titre": "Entrée incomplète, nulle ou qui n'est pas un objet : erreur 500 au lieu de 422",
        "gravite": "Majeure",
        "exigences": ["EX06", "EX10", "EX11"],
        "constat": "Un champ absent ou à `null`, un corps JSON qui est une liste, un texte ou un nombre provoquent une exception non rattrapée (KeyError, TypeError) transformée en erreur 500.",
        "scenarios": ["S02", "S14", "S19", "S21"],
        "pannes": [],
        "regles": _regles(
            r"::test_valeurs_manquantes\[",
            r"::test_champ_obligatoire_absent\[",
            r"::test_objet_vide_liste_tous_les_champs_manquants$",
            r"::test_corps_non_objet_refuse\[",
            r"::test_schema_incorrect_refuse\[(lot_de_demandes|tableau_vide|chaine)\]",
            r"::test_age_type_ou_valeur_invalide\[nul\]",
            r"::test_montants_type_invalide\[nul-",
            r"::test_duree_invalide_refusee\[None-",
            r"::test_anciennete_invalide\[None-",
        ),
        "cause": "`valider_demande` lit `payload[champ]` sans vérifier la présence du champ ni la forme du corps, et ne rattrape que `ValueError`.",
        "correction": "Validation stricte : le corps doit être un objet, chaque champ est vérifié (présence, type, domaine) et toutes les anomalies sont collectées puis renvoyées ensemble dans un 422 `donnees_invalides`.",
    },
    {
        "id": "A-02",
        "titre": "Valeurs non finies ou démesurées (NaN, Infinity, 1e999, entier géant) : erreur 500",
        "gravite": "Majeure",
        "exigences": ["EX02", "EX08", "EX10"],
        "constat": "Les constantes non standard `NaN`/`Infinity` acceptées par le décodeur JSON de Python, les exposants débordants (`1e999`) et les entiers géants (`10^400`) atteignent le prétraitement ou la conversion en flottant et font échouer la requête (500).",
        "scenarios": ["S15", "S16", "S26"],
        "pannes": [],
        "regles": _regles(
            r"::test_constantes_non_standard_refusees\[",
            r"::test_infinis_par_debordement_refuses\[",
            r"::test_montants_non_finis_refuses\[",
            r"::test_age_hors_limites_refuse\[",
            r"::test_age_type_ou_valeur_invalide\[(nan|infini)\]",
            r"::test_duree_invalide_refusee\[(nan|inf)-",
            r"::test_anciennete_invalide\[nan-",
        ),
        "cause": "Aucun contrôle de finitude ; `float()` appliqué à un entier géant lève `OverflowError` ; `json.loads` accepte `NaN` et `Infinity` hors norme RFC 8259.",
        "correction": "Rejet des constantes non standard au décodage (400 `json_invalide`), contrôle `math.isfinite`, comparaison aux bornes avant toute conversion (sûre pour un entier géant).",
    },
    {
        "id": "A-03",
        "titre": "Conversion implicite des types : « 250000 », `true`, « NaN », « Infinity » acceptés comme des nombres",
        "gravite": "Majeure",
        "exigences": ["EX01", "EX02", "EX03", "EX08", "EX12"],
        "constat": "Une chaîne numérique est convertie sans avertissement, un booléen devient 0 ou 1, des chiffres arabes, la chaîne « NaN » ou la chaîne « Infinity » sont acceptés : une prédiction (ou une erreur 500) est produite à partir d'une donnée qui ne respecte pas le contrat.",
        "scenarios": ["S05", "S20"],
        "pannes": [],
        "regles": _regles(
            r"::test_valeurs_non_numeriques\[",
            r"::test_age_type_ou_valeur_invalide\[(texte|vrai|faux|liste|objet)\]",
            r"::test_montants_type_invalide\[(?!nul-)",
            r"::test_duree_invalide_refusee\[(12|True)-type_invalide\]",
            r"::test_anciennete_invalide\[4-type_invalide\]",
            r"::test_schema_incorrect_refuse\[valeurs_dans_des_listes\]",
        ),
        "cause": "`float(payload[champ])` applique les règles de conversion de Python au lieu de contrôler le type JSON reçu.",
        "correction": "Aucune conversion implicite : seul un nombre JSON est accepté, les booléens sont explicitement exclus, le message d'erreur ne reproduit jamais la valeur reçue.",
    },
    {
        "id": "A-04",
        "titre": "Troncature silencieuse d'une valeur entière (durée 12,5 mois devient 12)",
        "gravite": "Moyenne",
        "exigences": ["EX01", "EX03"],
        "constat": "La durée et l'âge sont tronqués par `int()` : 12,5 mois est traité comme 12 mois, ce qui fausse le taux d'effort sans aucun signal.",
        "scenarios": ["S08"],
        "pannes": [],
        "regles": _regles(
            r"::test_duree_invalide_refusee\[(12\.5|0\.5)-non_entier\]",
            r"::test_age_type_ou_valeur_invalide\[decimal\]",
        ),
        "cause": "`int(duree)` appliqué après `float()`, sans vérifier que la partie fractionnaire est nulle.",
        "correction": "Une valeur entière attendue doit être un entier ou un flottant entier (35 ou 35.0) ; toute partie fractionnaire non nulle est refusée (`non_entier`).",
    },
    {
        "id": "A-05",
        "titre": "Bornes métier absentes ou incomplètes (montant nul, aucun plafond)",
        "gravite": "Majeure",
        "exigences": ["EX01", "EX02", "EX03", "EX08", "EX12"],
        "constat": "Un montant égal à 0 est accepté puis provoque `log(0)` (500) ; aucun plafond n'existe pour le revenu, le montant et l'ancienneté ; les anomalies de plusieurs champs ne sont pas toutes rapportées.",
        "scenarios": ["S06", "S10"],
        "pannes": [],
        "regles": _regles(
            r"::test_montants_hors_limites_refuses\[",
            r"::test_limites_depassees_refusees\[",
            r"::test_plafond_revenu_depasse_par_un$",
            r"::test_anciennete_invalide\[61-",
            r"::test_anomalies_cumulees_et_valeur_recue_jamais_reproduite$",
            r"::test_distinction_entree_invalide_et_entree_inhabituelle$",
        ),
        "cause": "Seuls l'âge, le revenu (> 0) et la durée sont bornés ; le montant n'est refusé que s'il est négatif ; ni plafond ni ancienneté maximale.",
        "correction": "Domaine de validité déclaré pour chaque champ (`config.LIMITES`, bornes incluses) et appliqué à tous ; les anomalies sont cumulées.",
    },
    {
        "id": "A-06",
        "titre": "Schéma non strict : champs supplémentaires, clés dupliquées, casse et alias ignorés ou mal gérés",
        "gravite": "Moyenne",
        "exigences": ["EX09"],
        "constat": "Un champ non prévu (par exemple `genre`) est ignoré sans signal ; une clé dupliquée est résolue silencieusement (la dernière gagne) ; `Age` ou un alias anglais sont traités comme des champs manquants (500).",
        "scenarios": ["S09", "S27"],
        "pannes": [],
        "regles": _regles(
            r"::test_champs_supplementaires_refuses_et_tries$",
            r"::test_cles_proches_ou_en_majuscules_refusees\[",
            r"::test_nom_de_champ_inconnu_tronque$",
            r"::test_schema_incorrect_refuse\[(casse_differente|imbrique|alias_anglais|champ_supplementaire_imbrique)\]",
        ),
        "cause": "La validation lit les cinq champs attendus et ne regarde jamais les autres clés du corps.",
        "correction": "Schéma strict : tout champ non autorisé est refusé (422 `champ_non_autorise`, noms triés et tronqués) ; une clé dupliquée rend la requête ambiguë (400 `json_invalide`).",
    },
    {
        "id": "A-07",
        "titre": "Incohérence entre l'âge et l'ancienneté d'activité non contrôlée",
        "gravite": "Moyenne",
        "exigences": ["EX12"],
        "constat": "Un demandeur de 20 ans avec 15 ans d'ancienneté est accepté et scoré.",
        "scenarios": ["S22"],
        "pannes": [],
        "regles": _regles(r"::test_incoherence_age_anciennete_refusee\["),
        "cause": "Aucun contrôle inter-champs.",
        "correction": "L'ancienneté ne peut pas dépasser l'âge moins 16 ans (422 `incoherence`).",
    },
    {
        "id": "A-08",
        "titre": "JSON mal formé, corps vide ou octets non décodables : erreur 500",
        "gravite": "Majeure",
        "exigences": ["EX10", "EX11"],
        "constat": "Un JSON tronqué, un corps vide ou des octets invalides ne sont pas rattrapés par le gestionnaire de la route et produisent une erreur 500.",
        "scenarios": ["S12", "S13"],
        "pannes": [],
        "regles": _regles(r"::test_octets_invalides_refuses\["),
        "cause": "Le décodage (`request.json()`) est exécuté dans le bloc générique `except Exception` de la route : une erreur de syntaxe devient une erreur 500.",
        "correction": "Toute erreur de décodage devient un 400 `json_invalide` au format d'erreur uniforme.",
    },
    {
        "id": "A-09",
        "titre": "Type de contenu non vérifié : un corps `text/plain` est traité",
        "gravite": "Moyenne",
        "exigences": ["EX10"],
        "constat": "Une requête envoyée avec `Content-Type: text/plain` est acceptée et scorée.",
        "scenarios": ["S17"],
        "pannes": [],
        "regles": _regles(),
        "cause": "L'en-tête `Content-Type` n'est pas contrôlé.",
        "correction": "Rejet 415 `type_contenu_non_supporte` si le type n'est pas `application/json`.",
    },
    {
        "id": "A-10",
        "titre": "Aucune limite de taille ni de profondeur : corps volumineux ou très imbriqué provoque une erreur 500",
        "gravite": "Majeure",
        "exigences": ["EX10"],
        "constat": "Un corps de 1 Mo ou un JSON imbriqué sur 4 900 niveaux (9,8 Ko) fait échouer la requête (500) : risque de déni de service.",
        "scenarios": ["S18", "S25"],
        "pannes": [],
        "regles": _regles(),
        "cause": "Le corps est lu et décodé sans limite ; la récursion du décodeur n'est pas maîtrisée.",
        "correction": "Rejet 413 au-delà de 10 000 octets (annoncés ou réellement lus) ; `RecursionError` traité comme un JSON invalide.",
    },
    {
        "id": "A-11",
        "titre": "Erreurs 500 qui exposent la trace, le message de l'exception et des chemins ; pas de code d'erreur distinct",
        "gravite": "Majeure",
        "exigences": ["EX11"],
        "constat": "Les réponses 500 contiennent `message = str(exc)` et la trace complète (chemins de fichiers du serveur, extraits de code, valeurs). Toutes les pannes internes portent le même code `erreur_interne`.",
        "scenarios": [],
        "pannes": ["P-prediction_exception"],
        "regles": _regles(
            r"::test_exception_imprevue_donne_une_erreur_generique$",
            r"::test_erreur_interne_pendant_la_prediction$",
        ),
        "cause": "Le bloc `except Exception` de la route renvoie `str(exc)` et `traceback.format_exc()` au client.",
        "correction": "Message générique côté client ; le détail est journalisé côté serveur et relié par un identifiant de requête (`id_requete`, `X-Request-ID`) ; codes distincts `erreur_pretraitement`, `erreur_prediction`, `incoherence_dimensions`.",
    },
    {
        "id": "A-12",
        "titre": "Modèle indisponible mal géré : erreur 500 avec chemin du fichier, `/health` toujours 200, pas de reprise",
        "gravite": "Majeure",
        "exigences": ["EX05", "EX11"],
        "constat": "Si le fichier du modèle ou des métadonnées est absent, illisible ou altéré, `/predict` renvoie une erreur 500 (avec la trace) et `/health` répond 200 « ok ».",
        "scenarios": ["S11"],
        "pannes": [
            "M-fichier_absent",
            "M-octets_aleatoires",
            "M-fichier_altere",
            "M-metadonnees_illisibles",
            "M-metadonnees_absentes",
        ],
        "regles": _regles(
            r"::test_validation_prioritaire_sur_la_disponibilite_du_modele$",
            r"::test_health_signale_l_indisponibilite_du_modele$",
            r"::test_indisponibilite_coherente_sur_les_trois_endpoints$",
            r"::test_reprise_automatique_apres_indisponibilite$",
            r"::test_modele_non_chargeable_est_signale_proprement\[(fichier_absent|octets_aleatoires|fichier_altere|metadonnees_illisibles|metadonnees_absentes)\]",
        ),
        "cause": "`charger()` laisse remonter les exceptions brutes ; `/health` ne consulte pas l'état du modèle.",
        "correction": "`ModeleIndisponible` unique ; 503 `modele_indisponible` avec `Retry-After` sur les trois endpoints ; `/health` répond 503 ; rechargement automatique à la requête suivante ; une demande invalide reste refusée en 422 même sans modèle.",
    },
    {
        "id": "A-13",
        "titre": "Aucun contrôle d'intégrité ni de conformité du modèle chargé",
        "gravite": "Critique",
        "exigences": ["EX14"],
        "constat": "Un modèle substitué, un fichier complété d'octets, une empreinte erronée, un modèle à 5 variables, un objet qui n'est pas un modèle, des métadonnées incomplètes ou aux variables permutées sont chargés et servent des prédictions (200).",
        "scenarios": [],
        "pannes": [
            "M-objet_non_conforme",
            "M-modele_a_5_variables",
            "M-metadonnees_incompletes",
            "M-variables_divergentes",
            "M-modele_substitue",
            "M-octets_ajoutes",
            "M-empreinte_metadonnees_erronee",
        ],
        "regles": _regles(
            r"::test_modele_non_chargeable_est_signale_proprement\[(objet_non_conforme|modele_a_5_variables|metadonnees_incompletes|variables_divergentes|modele_substitue|octets_ajoutes|empreinte_metadonnees_erronee)\]",
            r"::test_empreinte_non_conforme_refuse_le_modele_sans_le_deserialiser\[",
        ),
        "cause": "`charger()` désérialise directement le fichier avec `joblib.load` (format pickle, qui exécute du code à la lecture) sans comparer l'empreinte SHA-256 ni vérifier le contrat des métadonnées.",
        "correction": "Contrôles avant désérialisation : métadonnées complètes et variables conformes au prétraitement, empreinte SHA-256 identique ; contrôle du contrat de l'objet chargé (méthodes, nombre de variables, classes). Tout échec produit `ModeleIndisponible`.",
    },
    {
        "id": "A-14",
        "titre": "Prétraitement sans garde : `log(0)`, division par zéro, variable absente, exceptions brutes",
        "gravite": "Majeure",
        "exigences": ["EX02", "EX06", "EX08", "EX11"],
        "constat": "Le prétraitement produit silencieusement des infinis ou des NaN (avertissements NumPy) et laisse remonter des exceptions non typées lorsqu'une variable manque.",
        "scenarios": [],
        "pannes": ["P-variable_absente", "P-pretraitement_controle", "P-pretraitement_imprevu"],
        "regles": _regles(
            r"::test_pretraitement_refuse_les_entrees_non_transformables\[",
            r"::test_variable_attendue_absente_du_pretraitement$",
            r"::test_variable_attendue_absente_apres_validation$",
            r"::test_erreur_de_pretraitement_ne_fuit_pas_et_est_journalisee$",
        ),
        "cause": "`ErreurPretraitement` est déclarée mais jamais levée ; aucun contrôle des erreurs flottantes ni de la finitude de la matrice produite.",
        "correction": "Erreurs flottantes transformées en exception (`np.errstate(all='raise')`), vérification de la finitude du résultat, variable absente convertie en `ErreurPretraitement` (500 `erreur_pretraitement`, message générique).",
    },
    {
        "id": "A-15",
        "titre": "Aucune garde sur le modèle : dimensions incohérentes et probabilités invalides transmises",
        "gravite": "Critique",
        "exigences": ["EX04", "EX11", "EX16"],
        "constat": "Une probabilité de 1,5 ou de -0,1 renvoyée par le modèle est transmise à l'agent de crédit (200) ; NaN et infini produisent une erreur 500 sans corps JSON ; une matrice (2, 6) est acceptée ; (1, 5) et (1, 7) donnent une erreur 500 brute.",
        "scenarios": [],
        "pannes": [
            "D-1x5",
            "D-1x7",
            "D-2x6",
            "P-proba_nan",
            "P-proba_1.5",
            "P-proba_-0.1",
            "P-proba_inf",
        ],
        "regles": _regles(
            r"::test_dimensions_incompatibles_avec_le_modele\[",
            r"::test_probabilite_invalide_du_modele_jamais_transmise\[",
            r"::test_entree_non_finie_ou_non_numerique_refusee_par_le_service$",
            r"::test_probabilite_invalide_refusee_par_l_interpretation\[",
        ),
        "cause": "`predire` renvoie `float(predict_proba(x)[0, 1])` sans contrôler la forme de l'entrée ni la valeur de la sortie ; `interpreter_probabilite` n'a pas de garde.",
        "correction": "Contrôle de forme et de finitude avant l'inférence (`ErreurDimensions`), contrôle de la probabilité après (finie, dans [0 ; 1]) et garde dans l'interprétation : toute violation devient une erreur 500 générique et journalisée, jamais une probabilité.",
    },
    {
        "id": "A-16",
        "titre": "Version du modèle codée en dur et incohérente avec les métadonnées (« 1.0 » au lieu de « 1.0.0 »)",
        "gravite": "Moyenne",
        "exigences": ["EX13", "EX14"],
        "constat": "`/predict` annonce la version « 1.0 » alors que le modèle et ses métadonnées sont en 1.0.0 : la réponse n'est pas auditable.",
        "scenarios": [],
        "pannes": [],
        "regles": _regles(
            r"::test_contrat_de_reponse_predict$",
            r"::test_pipeline_de_bout_en_bout_et_metadonnees_coherentes$",
        ),
        "cause": "Constante de version dans le code de l'API.",
        "correction": "La version annoncée est lue dans les métadonnées du modèle réellement chargé.",
    },
    {
        "id": "A-17",
        "titre": "`/model-info` expose le chemin du fichier du modèle ; les métadonnées internes sont modifiables depuis l'extérieur",
        "gravite": "Moyenne",
        "exigences": ["EX07", "EX11", "EX14"],
        "constat": "La réponse contient `chemin_modele` (chemin absolu du fichier sur le serveur) ; la propriété `metadonnees` du service renvoie l'objet interne et non une copie : un appelant peut falsifier les métadonnées du service.",
        "scenarios": [],
        "pannes": [],
        "regles": _regles(
            r"::test_model_info_n_expose_ni_chemin_ni_version_de_bibliotheque$",
            r"::test_metadonnees_exposees_sans_fuite_de_references_internes$",
            r"::test_contrat_des_sorties_inchange$",
        ),
        "cause": "La réponse reprend `str(service.chemin_modele)` et la propriété `metadonnees` expose l'objet interne.",
        "correction": "Liste blanche de champs exposés (version, variables, empreinte, métriques de référence, seuils), sans chemin ; copie profonde des métadonnées.",
    },
    {
        "id": "A-18",
        "titre": "Contrat d'API incomplet : 404 et 405 hors format uniforme, schéma de requête absent de l'OpenAPI",
        "gravite": "Moyenne",
        "exigences": ["EX09", "EX10"],
        "constat": "Les erreurs 404 et 405 reprennent le format par défaut du framework ; la documentation OpenAPI ne décrit ni le corps de requête ni les erreurs.",
        "scenarios": ["S23", "S24"],
        "pannes": [],
        "regles": _regles(r"::test_contrat_openapi_documente_endpoints_et_schema$"),
        "cause": "Gestionnaires d'erreurs HTTP par défaut ; route sans modèle de requête déclaré.",
        "correction": "Gestionnaire d'exceptions HTTP au format uniforme (`ressource_introuvable`, `methode_non_autorisee`) ; schéma de requête et codes d'erreur documentés dans l'OpenAPI.",
    },
    {
        "id": "A-19",
        "titre": "Seuil de risque élevé mal appliqué : p = 0,60 est classé « modéré »",
        "gravite": "Majeure",
        "exigences": ["EX16"],
        "constat": "La règle attendue est p ≥ 0,60 → « élevé » ; le code compare avec `<=`.",
        "scenarios": [],
        "pannes": [],
        "regles": _regles(r"::test_niveaux_de_risque_aux_bornes\["),
        "cause": "Opérateur de comparaison `<=` au lieu de `<` à la borne.",
        "correction": "`p < 0,30` faible ; `0,30 ≤ p < 0,60` modéré ; `p ≥ 0,60` élevé, avec tests aux bornes (0, 0,2999, 0,30, 0,5999, 0,60, 1).",
    },
    {
        "id": "A-20",
        "titre": "Alertes « hors domaine d'entraînement » non implémentées (fonction vide)",
        "gravite": "Majeure",
        "exigences": ["EX04", "EX15"],
        "constat": "Une demande valide mais très éloignée des données d'entraînement (revenu de 20 millions, montant de 200 millions, durée de 120 mois…) est scorée sans aucun avertissement : fausse confiance dans une extrapolation.",
        "scenarios": [],
        "pannes": [],
        "regles": _regles(
            r"::test_alerte_hors_domaine\[",
            r"::test_alerte_sur_taux_d_effort_aberrant$",
            r"::test_entrees_atypiques_valides_signalees\[",
        ),
        "cause": "`evaluer_alertes` renvoie une liste vide (marquée TODO).",
        "correction": "Comparaison de chaque champ et du taux d'effort au domaine observé à l'entraînement (métadonnées du modèle) ; alerte `hors_domaine_entrainement` portée par la réponse 200.",
    },
]

TRANSVERSAL = {
    "id": "T-00",
    "titre": "Symptôme transversal : le fuzzing de 800 requêtes ne doit produire aucune erreur serveur",
    "regles": [r"::test_fuzzing_aucune_erreur_serveur$"],
    "explication": "Cumul des causes A-01, A-02, A-08 et A-10 : aucun défaut propre.",
}


# --------------------------------------------------------------------------------------------
def fr(nombre: float, decimales: int = 3) -> str:
    return f"{nombre:.{decimales}f}".replace(".", ",")


def mil(nombre: int) -> str:
    """Entier avec séparateur de milliers insécable (usage français)."""
    return f"{nombre:,}".replace(",", "\u00a0")


def pct(nombre: float, decimales: int = 1) -> str:
    return f"{100 * nombre:.{decimales}f}".replace(".", ",") + " %"


def charger(chemin: Path):
    return json.loads(chemin.read_text(encoding="utf-8"))


def attribuer(tests_v1: list[dict], tests_v2: list[dict]) -> dict:
    """Rattache chaque test à son anomalie ; vérifie l'unicité et l'exhaustivité des échecs."""
    regles: list[tuple[str, str]] = []
    for a in ANOMALIES:
        regles += [(a["id"], motif) for motif in a["regles"]]
        regles += [(a["id"], rf"::test_scenarios_api\[{s}\]$") for s in a["scenarios"]]
    regles += [(TRANSVERSAL["id"], motif) for motif in TRANSVERSAL["regles"]]

    def correspondances(noeud: str) -> set[str]:
        return {identifiant for identifiant, motif in regles if re.search(motif, noeud)}

    par_anomalie: dict[str, dict] = {
        identifiant: {"rattaches": 0, "echecs_v0_1": 0, "reussis_v0_2": 0, "echecs_v0_2": 0}
        for identifiant in [a["id"] for a in ANOMALIES] + [TRANSVERSAL["id"]]
    }
    erreurs = []
    for test in tests_v1:
        cibles = correspondances(test["test"])
        if test["resultat"] == "failed" and len(cibles) != 1:
            erreurs.append((test["test"], sorted(cibles)))
        for identifiant in cibles:
            par_anomalie[identifiant]["rattaches"] += 1
            par_anomalie[identifiant]["echecs_v0_1"] += test["resultat"] == "failed"
    for test in tests_v2:
        for identifiant in correspondances(test["test"]):
            par_anomalie[identifiant]["reussis_v0_2"] += test["resultat"] == "passed"
            par_anomalie[identifiant]["echecs_v0_2"] += test["resultat"] == "failed"
    if erreurs:
        raise SystemExit(f"échecs non rattachés à exactement une anomalie : {erreurs[:10]}")
    return par_anomalie


def constats_ouverts(audit: dict, perf: dict, non_regression: dict) -> list[dict]:
    pires = {s["segment"]: s for s in audit["pires_segments"]}
    glob = audit["global"]
    long_ = pires[">= 24 mois"]
    croise = pires["< 2 ans & >= 24 mois"]
    balayage = {b["seuil"]: b for b in audit["balayage_seuils"]}
    s10, s20 = balayage[0.1], balayage[0.2]
    cas = {c["id"]: c for c in charger(RACINE / "tests/reference/cas_dores.json")}
    essai_1 = perf["charge_essai_precedent"]
    return [
        {
            "id": "O-01",
            "titre": "Taux de faux négatifs très élevé sur des profils précis, invisible dans les indicateurs globaux",
            "gravite": "Critique",
            "exigences": ["EX07", "EX16"],
            "constat": (
                f"Au seuil de décision {fr(audit['seuil_decision'], 2)}, le rappel global est de {fr(glob['rappel'])} "
                f"(faux négatifs : {pct(glob['taux_faux_negatifs'])}), avec une AUC de {fr(glob['auc_roc'])} et une erreur de "
                f"calibration de {fr(audit['ece'])}. Pour les prêts de 24 mois ou plus (n = {mil(long_['n'])}, {long_['defauts']} "
                f"défauts), le rappel tombe à {fr(long_['rappel'])} (faux négatifs : {pct(long_['taux_faux_negatifs'])}) ; "
                f"pour les demandeurs de moins de 2 ans d'ancienneté avec un prêt de 24 mois ou plus (n = {mil(croise['n'])}, "
                f"{croise['defauts']} défauts), il est de {fr(croise['rappel'])} ({croise['faux_negatifs']} défauts sur "
                f"{croise['defauts']} non signalés). Tous les tests fonctionnels et de non-régression passent."
            ),
            "preuve": "reports/audit_segments.md (données synthétiques ; l'interaction durée × ancienneté a été introduite volontairement dans le générateur pour que l'audit ait quelque chose à trouver)",
            "action": f"Ouvert : décision métier. Pistes : seuil adapté ou revue manuelle obligatoire pour les prêts de 24 mois ou plus (au seuil 0,20 le rappel global passe à {fr(s20['rappel'])} et à {fr(s20['rappel[>= 24 mois]'])} pour les prêts longs, avec {pct(s20['part_dossiers_signales'])} de dossiers signalés ; au seuil 0,10 : {fr(s10['rappel'])} et {fr(s10['rappel[>= 24 mois]'])}, mais {pct(s10['part_dossiers_signales'])} de dossiers signalés), critères d'acceptation par segment dans la non-régression, réentraînement avec interaction ou modèle non linéaire.",
        },
        {
            "id": "O-02",
            "titre": "Extrapolation hors du domaine d'entraînement : probabilités extrêmes ou trompeuses malgré l'alerte",
            "gravite": "Majeure",
            "exigences": ["EX15"],
            "constat": (
                f"Le cas doré G16 (montant de 60 millions, hors du domaine d'entraînement) obtient une probabilité de défaut de "
                f"{fr(cas['G16']['probabilite_reference'], 5)} ; le cas G15 (revenu de 8 millions) obtient "
                f"{fr(cas['G15']['probabilite_reference'], 4)}. L'alerte `hors_domaine_entrainement` est émise, mais la "
                "probabilité reste renvoyée comme les autres."
            ),
            "preuve": "tests/reference/cas_dores.json (G15, G16), tests de robustesse EX15",
            "action": "Ouvert : décider si une demande hors domaine doit être orientée vers une revue manuelle sans score affiché.",
        },
        {
            "id": "O-03",
            "titre": "Aucune authentification, aucun chiffrement de transport, aucune limitation de débit",
            "gravite": "Majeure",
            "exigences": ["EX10", "EX11"],
            "constat": "L'API est ouverte : tout client qui l'atteint peut interroger `/predict` et `/model-info`, sans trace d'audit des décisions ni limite de débit.",
            "preuve": "Conception du prototype (hors périmètre de la consigne)",
            "action": "Ouvert : à traiter avant tout déploiement (authentification, TLS, quota, journal d'audit sans donnée personnelle superflue).",
        },
        {
            "id": "O-04",
            "titre": "Chargement du modèle par pickle : l'empreinte protège contre l'erreur, pas contre un attaquant qui écrit les deux fichiers",
            "gravite": "Majeure",
            "exigences": ["EX14"],
            "constat": "Le contrôle SHA-256 détecte une corruption ou une substitution accidentelle et empêche de désérialiser un fichier inattendu, mais l'empreinte attendue est stockée à côté du modèle.",
            "preuve": "tests TC14 et TC15 ; app/prediction.py",
            "action": "Ouvert : signer le modèle ou publier l'empreinte par un canal distinct, restreindre les droits d'écriture, envisager un format sans exécution de code.",
        },
        {
            "id": "O-05",
            "titre": "Aucune analyse d'équité ni de conformité réglementaire ; l'âge est une variable explicative",
            "gravite": "Majeure",
            "exigences": [],
            "constat": "Les écarts de performance entre groupes (âge, genre, zone) ne sont ni mesurés ni encadrés ; l'usage de l'âge dans un modèle de crédit peut être restreint selon le cadre juridique applicable.",
            "preuve": "Hors périmètre des tests ; audit limité aux segments d'âge, d'ancienneté, de revenu et de durée",
            "action": "Ouvert : analyse d'impact et d'équité par la conformité avant tout usage décisionnel.",
        },
        {
            "id": "O-06",
            "titre": "Données exclusivement synthétiques : aucune conclusion sur la performance réelle",
            "gravite": "Critique",
            "exigences": [],
            "constat": "Le jeu d'entraînement et le jeu d'évaluation sont générés par un modèle probabiliste écrit pour l'exercice ; les métriques mesurent la cohérence du système, pas la qualité d'un score de crédit.",
            "preuve": "data/DONNEES.md",
            "action": "Ouvert : le modèle doit être requalifié (mêmes tests, baseline, audit par segment) sur des données réelles, anonymisées et représentatives.",
        },
        {
            "id": "O-07",
            "titre": "Exploitation : instance unique, aucune supervision de la dérive ni de la performance en production",
            "gravite": "Moyenne",
            "exigences": ["EX05", "EX17"],
            "constat": "Un seul processus sert l'API ; rien ne surveille la distribution des entrées, la calibration ou le rappel par segment une fois en service.",
            "preuve": "Architecture du prototype",
            "action": "Ouvert : redondance, métriques d'exploitation, suivi de dérive et de calibration, procédure de retour arrière documentée.",
        },
        {
            "id": "O-08",
            "titre": "Rares échecs de connexion persistante (statut 0) sous charge soutenue",
            "gravite": "Mineure",
            "exigences": ["EX17"],
            "constat": (
                f"Lors d'un des deux essais de charge progressive, {essai_1['total_echecs']} requêtes sur "
                f"{mil(essai_1['total_requetes'])} ont échoué sans réponse ; l'essai final n'en compte aucun sur "
                f"{mil(perf['charge']['total_requetes'])}. Cause reproduite de façon déterministe : fermeture de la connexion "
                "inactive par uvicorn au bout de 5 s (`--timeout-keep-alive`) au moment où le client la réutilise."
            ),
            "preuve": "reports/performance/essai_keep_alive.txt",
            "action": "Atténuation documentée : aligner les délais (client plus court que le serveur) ou placer un reverse proxy ; nouvelle tentative côté client pour les requêtes idempotentes.",
        },
        {
            "id": "O-09",
            "titre": "Message de recommandation « Profil standard : poursuivre l'instruction habituelle » au niveau faible",
            "gravite": "Majeure",
            "exigences": ["EX16"],
            "constat": "Un niveau « faible » est présenté comme un profil standard à instruire normalement, alors que le modèle laisse passer une part importante de défauts dans certains segments (O-01) : le texte rassure plus que ce que les preuves permettent.",
            "preuve": "app/prediction.py (`interpreter_probabilite`)",
            "action": "Ouvert : reformuler (« aucun signal de risque élevé détecté par le modèle ; ne dispense pas de l'analyse habituelle ») après validation par le métier.",
        },
        {
            "id": "O-10",
            "titre": "Seuils de risque 0,30 et 0,60 non validés par le métier",
            "gravite": "Moyenne",
            "exigences": ["EX16"],
            "constat": "Les seuils sont ceux de l'énoncé ; aucune analyse de coût (crédit accordé à tort, dossier refusé à tort, charge de revue) ne les justifie.",
            "preuve": "reports/audit_segments.md (balayage de seuils)",
            "action": "Ouvert : décision métier fondée sur le balayage de seuils et la capacité de revue.",
        },
    ]


def lacune_de_tests() -> dict:
    return {
        "id": "T-01",
        "titre": "Lacune de la suite de tests : la désactivation du contrôle SHA-256 n'était détectée par aucun test",
        "gravite": "Majeure",
        "exigences": ["EX14"],
        "constat": "L'injection de défauts dans le code (`scripts/preuve_ci.py`, mutant M4 : contrôle d'empreinte remplacé par `if False`) laissait la suite entièrement verte : le défaut « fichier altéré » échouait par un autre chemin (le fichier modifié n'était plus chargeable) et masquait l'absence de contrôle.",
        "action": "Corrigée : trois défauts silencieux (modèle substitué, octets ajoutés, empreinte des métadonnées erronée), un test exigeant que le fichier suspect ne soit jamais désérialisé et un témoin positif (cas de test TC15). Les 15 défauts injectés sont désormais tous détectés (reports/preuve_ci_locale.md).",
    }


def ecrire(chemin_md: Path, chemin_json: Path) -> None:
    c1 = charger(RAPPORTS / "campagne1_v0.1" / "resultats_tests.json")["tests"]
    c2 = charger(RAPPORTS / "campagne2_v0.2" / "resultats_tests.json")["tests"]
    m1 = charger(RAPPORTS / "campagne1_v0.1" / "meta.json")
    m2 = charger(RAPPORTS / "campagne2_v0.2" / "meta.json")
    api1 = {x["id"]: x for x in charger(RAPPORTS / "campagne1_v0.1" / "resultats_api.json")}
    api2 = {x["id"]: x for x in charger(RAPPORTS / "campagne2_v0.2" / "resultats_api.json")}
    pannes1 = {x["id"]: x for x in charger(RAPPORTS / "campagne1_v0.1" / "pannes.json")}
    pannes2 = {x["id"]: x for x in charger(RAPPORTS / "campagne2_v0.2" / "pannes.json")}
    fuzz1 = charger(RAPPORTS / "campagne1_v0.1" / "fuzzing.json")
    fuzz2 = charger(RAPPORTS / "campagne2_v0.2" / "fuzzing.json")
    audit = charger(RAPPORTS / "audit_segments.json")
    perf = charger(RAPPORTS / "performance" / "performance.json")
    non_regression = charger(RAPPORTS / "non_regression.json")

    comptes = attribuer(c1, c2)
    echecs_v1 = sum(t["resultat"] == "failed" for t in c1)
    attribues = sum(v["echecs_v0_1"] for v in comptes.values())
    assert attribues == echecs_v1, (attribues, echecs_v1)

    # Enrichissement des fiches avec les preuves lues dans les campagnes.
    fiches = []
    for a in ANOMALIES:
        fiche = {
            k: a[k]
            for k in ("id", "titre", "gravite", "exigences", "constat", "cause", "correction")
        }
        fiche["tests"] = comptes[a["id"]]
        fiche["scenarios"] = [
            {
                "id": s,
                "titre": api1[s]["titre"],
                "attendu": f"{api1[s]['statut_attendu']} {api1[s]['erreur_attendue'] or ''}".strip(),
                "observe_v0_1": f"{api1[s]['statut_observe']} {api1[s]['erreur_observee'] or ''}".strip(),
                "fuite_technique_v0_1": api1[s]["fuite_technique"],
                "conforme_v0_2": api2[s]["conforme"],
            }
            for s in a["scenarios"]
        ]
        fiche["pannes"] = [
            {
                "id": p,
                "description": pannes1[p]["description"],
                "attendu": f"{pannes1[p]['statut_attendu']} {pannes1[p]['erreur_attendue'] or ''}".strip(),
                "observe_v0_1": f"{pannes1[p]['statut_observe']} {pannes1[p]['erreur_observee'] or ''}".strip(),
                "fuite_technique_v0_1": pannes1[p]["fuite_technique"],
                "conforme_v0_2": pannes2[p]["conforme"],
            }
            for p in a["pannes"]
        ]
        fiche["statut"] = "Corrigée en v0.2, vérifiée par la campagne 2"
        fiches.append(fiche)

    ouverts = constats_ouverts(audit, perf, non_regression)
    lacune = lacune_de_tests()

    par_gravite = {g: {"anomalies": 0, "tests_en_echec": 0} for g in ECHELLE_GRAVITE}
    for f in fiches:
        par_gravite[f["gravite"]]["anomalies"] += 1
        par_gravite[f["gravite"]]["tests_en_echec"] += f["tests"]["echecs_v0_1"]
    ouverts_par_gravite = {g: sum(o["gravite"] == g for o in ouverts) for g in ECHELLE_GRAVITE}

    fuites_scenarios = sum(x["fuite_technique"] for x in api1.values())
    fuites_pannes = sum(x["fuite_technique"] for x in pannes1.values())
    synthese = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "campagne_1": {
            "version": m1["version_application"],
            "commit_application": m1.get("commit_application"),
            "tests": m1["tests"],
            "couverture_pct": m1["couverture_pct"],
            "scenarios_conformes": sum(x["conforme"] for x in api1.values()),
            "scenarios_total": len(api1),
            "pannes_conformes": sum(x["conforme"] for x in pannes1.values()),
            "pannes_total": len(pannes1),
            "fuzzing": fuzz1,
            "fuites_techniques_scenarios": fuites_scenarios,
            "fuites_techniques_pannes": fuites_pannes,
        },
        "campagne_2": {
            "version": m2["version_application"],
            "commit_application": m2.get("commit_application"),
            "tests": m2["tests"],
            "couverture_pct": m2["couverture_pct"],
            "scenarios_conformes": sum(x["conforme"] for x in api2.values()),
            "scenarios_total": len(api2),
            "pannes_conformes": sum(x["conforme"] for x in pannes2.values()),
            "pannes_total": len(pannes2),
            "fuzzing": fuzz2,
        },
        "par_gravite": par_gravite,
        "constats_ouverts_par_gravite": ouverts_par_gravite,
        "echecs_v0_1": echecs_v1,
        "echecs_rattaches": attribues,
        "transversal": {**TRANSVERSAL, **comptes[TRANSVERSAL["id"]]},
    }
    chemin_json.write_text(
        json.dumps(
            {
                "synthese": synthese,
                "echelle_gravite": ECHELLE_GRAVITE,
                "anomalies": fiches,
                "constats_ouverts": ouverts,
                "lacune_de_tests": lacune,
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --- Markdown -------------------------------------------------------------------------
    s1, s2 = synthese["campagne_1"], synthese["campagne_2"]
    md = [
        "# Registre des anomalies",
        "",
        f"Généré le {synthese['date']} par `python -m scripts.registre_anomalies` à partir des résultats des campagnes "
        "(`reports/campagne1_v0.1`, `reports/campagne2_v0.2`), de l'audit par segment et de la mesure de performance.",
        "",
        "## Lecture",
        "",
        f"- **Campagne 1** : code applicatif v{s1['version']} (commit {s1['commit_application']}), suite finale de "
        f"{s1['tests']['total']} tests : {s1['tests']['passed']} réussis, **{s1['tests']['failed']} en échec**, "
        f"{s1['tests']['skipped']} ignoré ; scénarios fonctionnels conformes : {s1['scenarios_conformes']} sur {s1['scenarios_total']} ; "
        f"injections de pannes conformes : {s1['pannes_conformes']} sur {s1['pannes_total']} ; fuzzing : "
        f"{s1['fuzzing']['erreurs_serveur']} erreurs serveur sur {s1['fuzzing']['n']} requêtes ({pct(s1['fuzzing']['taux_erreurs_serveur'])}) ; "
        f"fuite d'information technique dans {s1['fuites_techniques_scenarios']} scénarios sur {s1['scenarios_total']}.",
        f"- **Campagne 2** : code applicatif v{s2['version']}, mêmes tests : {s2['tests']['passed']} réussis, "
        f"**{s2['tests']['failed']} en échec**, {s2['tests']['skipped']} ignoré, couverture {fr(s2['couverture_pct'], 1)} % ; scénarios "
        f"conformes : {s2['scenarios_conformes']} sur {s2['scenarios_total']} ; pannes conformes : {s2['pannes_conformes']} sur "
        f"{s2['pannes_total']} ; fuzzing : {s2['fuzzing']['erreurs_serveur']} erreur serveur sur {s2['fuzzing']['n']} requêtes.",
        f"- Les **{echecs_v1} échecs** de la campagne 1 sont rattachés chacun à une seule cause racine "
        f"({attribues} rattachés : {attribues - comptes[TRANSVERSAL['id']]['echecs_v0_1']} aux {len(ANOMALIES)} anomalies, "
        f"{comptes[TRANSVERSAL['id']]['echecs_v0_1']} au test de fuzzing, symptôme cumulé de A-01, A-02, A-08 et A-10).",
        "- Le code v0.1 est le premier jet volontairement naïf du prototype : les anomalies ci-dessous sont des défauts "
        "réels détectés par la stratégie de test, pas des défauts simulés.",
        "",
        "## Échelle de gravité",
        "",
        "| Gravité | Définition |",
        "| :--- | :--- |",
    ]
    md += [f"| {g} | {d} |" for g, d in ECHELLE_GRAVITE.items()]
    md += [
        "",
        "## Synthèse par gravité",
        "",
        "| Gravité | Anomalies corrigées en v0.2 | Tests en échec en v0.1 | Constats ouverts |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for g in ECHELLE_GRAVITE:
        md.append(
            f"| {g} | {par_gravite[g]['anomalies']} | {par_gravite[g]['tests_en_echec']} | {ouverts_par_gravite[g]} |"
        )
    md += [
        f"| **Total** | **{len(ANOMALIES)}** | **{attribues - comptes[TRANSVERSAL['id']]['echecs_v0_1']}** | **{len(ouverts)}** |",
        "",
        "## Anomalies détectées en v0.1 et corrigées en v0.2",
        "",
        "| Id | Anomalie | Gravité | Exigences | Tests en échec v0.1 | Tests rattachés réussis en v0.2 | Statut |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | :--- |",
    ]
    for f in fiches:
        t = f["tests"]
        md.append(
            f"| {f['id']} | {f['titre']} | {f['gravite']} | {', '.join(f['exigences'])} | {t['echecs_v0_1']} | "
            f"{t['reussis_v0_2']} sur {t['reussis_v0_2'] + t['echecs_v0_2']} | Corrigée |"
        )
    md.append("")
    for f in fiches:
        t = f["tests"]
        md += [
            f"### {f['id']} — {f['titre']}",
            "",
            f"- **Gravité** : {f['gravite']} — **Exigences** : {', '.join(f['exigences'])}",
            f"- **Constat** : {f['constat']}",
        ]
        preuves = []
        for s in f["scenarios"]:
            preuves.append(
                f"scénario {s['id']} « {s['titre']} » : attendu {s['attendu']}, observé {s['observe_v0_1']}"
                + (" (avec fuite technique)" if s["fuite_technique_v0_1"] else "")
            )
        for p in f["pannes"]:
            preuves.append(
                f"injection {p['id']} « {p['description']} » : attendu {p['attendu']}, observé {p['observe_v0_1']}"
                + (" (avec fuite technique)" if p["fuite_technique_v0_1"] else "")
            )
        preuves.append(
            f"{t['echecs_v0_1']} test(s) en échec sur {t['rattaches']} rattachés en v0.1 ; "
            f"{t['reussis_v0_2']} sur {t['reussis_v0_2'] + t['echecs_v0_2']} réussis en v0.2"
        )
        md.append("- **Preuves** :")
        md += [f"  - {p}" for p in preuves]
        md += [
            f"- **Cause racine** : {f['cause']}",
            f"- **Correction** : {f['correction']}",
            f"- **Statut** : {f['statut']}",
            "",
        ]
    md += [
        "### T-00 — Symptôme transversal (fuzzing)",
        "",
        f"- {TRANSVERSAL['titre']} : v0.1 : {s1['fuzzing']['erreurs_serveur']} erreurs serveur sur {s1['fuzzing']['n']} requêtes "
        f"(statuts : {json.dumps(s1['fuzzing']['statuts'])}) ; v0.2 : {s2['fuzzing']['erreurs_serveur']} "
        f"(statuts : {json.dumps(s2['fuzzing']['statuts'])}). {TRANSVERSAL['explication']}",
        "",
        "## Constats ouverts (non corrigés par le prototype)",
        "",
        "Ces constats ne sont pas des défauts de code corrigeables par une retouche : ils relèvent de décisions "
        "métier, de conception ou de gouvernance. Ils conditionnent la conclusion sur la mise en production.",
        "",
        "| Id | Constat | Gravité | Statut |",
        "| :--- | :--- | :--- | :--- |",
    ]
    md += [f"| {o['id']} | {o['titre']} | {o['gravite']} | Ouvert |" for o in ouverts]
    md.append("")
    for o in ouverts:
        md += [
            f"### {o['id']} — {o['titre']}",
            "",
            f"- **Gravité** : {o['gravite']}"
            + (f" — **Exigences** : {', '.join(o['exigences'])}" if o["exigences"] else ""),
            f"- **Constat** : {o['constat']}",
            f"- **Preuve** : {o['preuve']}",
            f"- **Suite** : {o['action']}",
            "",
        ]
    md += [
        "## Lacune de la suite de tests découverte par injection de défauts",
        "",
        f"### {lacune['id']} — {lacune['titre']}",
        "",
        f"- **Gravité** : {lacune['gravite']} — **Exigences** : {', '.join(lacune['exigences'])}",
        f"- **Constat** : {lacune['constat']}",
        f"- **Suite** : {lacune['action']}",
        "",
    ]
    chemin_md.write_text("\n".join(md), encoding="utf-8")
    print(
        f"{len(ANOMALIES)} anomalies, {len(ouverts)} constats ouverts, "
        f"{attribues}/{echecs_v1} échecs rattachés -> {chemin_md.name}, {chemin_json.name}"
    )


if __name__ == "__main__":
    ecrire(RAPPORTS / "registre_anomalies.md", RAPPORTS / "registre_anomalies.json")
