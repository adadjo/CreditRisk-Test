"""Catalogue des exigences testables : source unique du plan de test et de la matrice de traçabilité.

La priorité est calculée, pas saisie : score = gravité x probabilité d'occurrence.
P1 : score >= 6 ; P2 : 3 à 5 ; P3 : <= 2.
"""

from __future__ import annotations

from dataclasses import dataclass

POIDS_GRAVITE = {"Critique": 4, "Majeure": 3, "Moyenne": 2, "Mineure": 1}
POIDS_PROBABILITE = {"Élevée": 3, "Moyenne": 2, "Faible": 1}


@dataclass(frozen=True)
class Exigence:
    id: str
    intitule: str
    resultat_attendu: str
    risque: str
    gravite: str
    probabilite: str
    preconditions: str
    donnees_entree: str
    niveaux: str
    origine: str = "Ajoutée"

    @property
    def score(self) -> int:
        return POIDS_GRAVITE[self.gravite] * POIDS_PROBABILITE[self.probabilite]

    @property
    def priorite(self) -> str:
        return "P1" if self.score >= 6 else "P2" if self.score >= 3 else "P3"


EXIGENCES: tuple[Exigence, ...] = (
    Exigence(
        "EX01",
        "L'âge est compris dans l'intervalle autorisé [18 ; 75]",
        "Les valeurs hors limites sont rejetées (422)",
        "Octroi à un mineur ou prédiction sur un âge aberrant",
        "Majeure",
        "Moyenne",
        "API démarrée, modèle chargé",
        'age = 17, 18, 75, 76, -5, 1 000 000, 35.5, "35", null',
        "Unitaire, API, robustesse",
        "Énoncé",
    ),
    Exigence(
        "EX02",
        "Le revenu est numérique, fini et positif",
        "Une entrée invalide provoque une erreur contrôlée (422/400)",
        "Division par zéro, log invalide, NaN propagé, erreur 500",
        "Majeure",
        "Élevée",
        "API démarrée, modèle chargé",
        'revenu = 0, -1, "abc", "250000", NaN, 1e999, 10^400, 20 000 001',
        "Unitaire, API, robustesse",
        "Énoncé",
    ),
    Exigence(
        "EX03",
        "La durée est un entier valide [1 ; 120] mois",
        "Les durées invalides sont rejetées, sans troncature silencieuse",
        "Taux d'effort faux (12,5 tronqué à 12), booléen assimilé à 1",
        "Moyenne",
        "Moyenne",
        "API démarrée, modèle chargé",
        'duree = 0, 1, 120, 121, 12.5, 12.0, true, "12"',
        "Unitaire, API, robustesse",
        "Énoncé",
    ),
    Exigence(
        "EX04",
        "La prédiction retourne une probabilité valide",
        "La probabilité est finie et comprise entre 0 et 1",
        "Résultat invalide présenté à l'agent de crédit",
        "Critique",
        "Moyenne",
        "Modèle chargé",
        "Demandes valides ; modèle simulé renvoyant NaN, -0,1 ou 1,5",
        "API, intégration, robustesse",
        "Énoncé",
    ),
    Exigence(
        "EX05",
        "Le modèle est disponible",
        "Une indisponibilité est signalée correctement (503, /health indisponible)",
        "Faux « OK », plantage ou erreur 500 brute si le modèle manque",
        "Majeure",
        "Moyenne",
        "Modèle absent, corrompu ou altéré",
        "Fichier inexistant, octets aléatoires, empreinte modifiée, objet non conforme",
        "API, intégration",
        "Énoncé",
    ),
    Exigence(
        "EX06",
        "Une entrée incomplète est soumise à validation",
        "Une réponse d'erreur appropriée est retournée (422 listant les champs)",
        "KeyError non maîtrisée (500) ou prédiction sur données partielles",
        "Majeure",
        "Élevée",
        "API démarrée, modèle chargé",
        "Chaque champ retiré tour à tour, objet vide, null, liste",
        "Unitaire, API, robustesse",
        "Énoncé",
    ),
    Exigence(
        "EX07",
        "Une nouvelle version ne dégrade pas les critères critiques",
        "Le contrôle de non-régression s'exécute et bloque une dégradation",
        "Dégradation silencieuse du rappel : octroi de crédits risqués",
        "Critique",
        "Moyenne",
        "Version de référence et tolérances figées",
        "Métriques sur jeu d'évaluation figé, cas dorés, candidats équivalent / amélioré / dégradé",
        "Non-régression",
        "Énoncé",
    ),
    Exigence(
        "EX08",
        "Le montant du crédit est numérique, strictement positif et plafonné",
        "Un montant nul, négatif ou aberrant est rejeté",
        "log(0) = -infini, taux d'effort aberrant, erreur 500",
        "Majeure",
        "Élevée",
        "API démarrée, modèle chargé",
        'montant = 0, -1 000 000, 1, 200 000 000, 200 000 001, "1 000 000"',
        "Unitaire, API, robustesse",
    ),
    Exigence(
        "EX09",
        "Les champs non autorisés sont rejetés (schéma strict)",
        "Un champ supplémentaire provoque un rejet 422 explicite",
        "Contrat flou, attribut sensible transmis puis ignoré sans contrôle",
        "Moyenne",
        "Moyenne",
        "API démarrée, modèle chargé",
        "Champ « genre », clés en majuscules, objets imbriqués",
        "Unitaire, API, robustesse",
    ),
    Exigence(
        "EX10",
        "Les requêtes mal formées sont traitées de façon contrôlée",
        "400, 405, 404, 413 ou 415 selon le cas, au format d'erreur uniforme",
        "Erreur 500 ou déni de service (corps volumineux, imbrication profonde)",
        "Majeure",
        "Élevée",
        "API démarrée",
        "JSON tronqué, corps vide, liste, 1 Mo, 4 900 niveaux d'imbrication, text/plain, GET /predict",
        "API, robustesse",
    ),
    Exigence(
        "EX11",
        "Les erreurs n'exposent aucune information technique sensible",
        "Aucune trace, aucun chemin ni message d'exception dans la réponse ; détail dans le journal",
        "Divulgation d'informations facilitant une attaque",
        "Majeure",
        "Moyenne",
        "Pannes injectées dans chaque étage du pipeline",
        "Exceptions contenant « secret », chemins de fichiers, noms de classes",
        "Intégration",
    ),
    Exigence(
        "EX12",
        "L'ancienneté d'activité est valide et cohérente avec l'âge",
        "Ancienneté dans [0 ; 60] et inférieure ou égale à âge - 16",
        "Données incohérentes qui faussent le risque",
        "Moyenne",
        "Moyenne",
        "API démarrée, modèle chargé",
        "age 20 / ancienneté 4 (limite), 4,5 (incohérent) ; ancienneté -1, 61",
        "Unitaire, API, robustesse",
    ),
    Exigence(
        "EX13",
        "Les résultats sont déterministes et reproductibles",
        "Mêmes entrées, mêmes sorties ; identique après sauvegarde/rechargement et réentraînement",
        "Décisions non reproductibles, donc non auditables",
        "Majeure",
        "Faible",
        "Modèle versionné, graine fixée",
        "20 appels identiques, ordre des clés, 35 vs 35.0, sauvegarde/rechargement, réentraînement",
        "Robustesse, non-régression",
    ),
    Exigence(
        "EX14",
        "Le modèle chargé est celui qui est documenté (intégrité et métadonnées)",
        "Version, variables et empreinte SHA-256 cohérentes entre fichier, /model-info et /predict",
        "Mauvais modèle chargé, fichier altéré ou malveillant (sérialisation pickle)",
        "Critique",
        "Faible",
        "Modèle et métadonnées versionnés",
        "Fichier intact, altéré, métadonnées incomplètes, variables divergentes",
        "Intégration, non-régression",
    ),
    Exigence(
        "EX15",
        "Les entrées atypiques mais valides sont signalées",
        "Réponse 200 accompagnée d'alertes hors_domaine_entrainement",
        "Fausse confiance dans une extrapolation du modèle",
        "Moyenne",
        "Élevée",
        "Domaine d'entraînement connu des métadonnées",
        "Revenu 15 M FCFA, crédit 150 M FCFA, durée 120 mois, âge 75",
        "Unitaire, robustesse",
    ),
    Exigence(
        "EX16",
        "La probabilité est interprétée en niveau de risque avec des seuils exacts",
        "p < 0,30 faible ; 0,30 <= p < 0,60 modéré ; p >= 0,60 élevé",
        "Mauvaise catégorie de risque aux bornes",
        "Majeure",
        "Moyenne",
        "Aucune",
        "p = 0, 0,2999, 0,30, 0,5999, 0,60, 1 ; valeurs invalides",
        "Unitaire, API",
    ),
    Exigence(
        "EX17",
        "Le système respecte les objectifs de performance",
        "P95 API <= 200 ms ; P95 inférence <= 20 ms ; débit >= 50 req/s",
        "Indisponibilité pratique, mauvaise expérience de l'agent",
        "Moyenne",
        "Faible",
        "Runner CPU standard",
        "200 requêtes séquentielles, charge progressive Locust",
        "Performance",
    ),
    Exigence(
        "EX18",
        "La chaîne CI exécute les tests et bloque en cas d'échec",
        "Workflow déclenché sur Pull Request avec Ruff, Pytest et couverture ; échec si un test échoue",
        "Régression non détectée avant fusion",
        "Moyenne",
        "Moyenne",
        "Dépôt GitHub",
        "tests.yml, test volontairement défaillant",
        "CI",
    ),
)

EXIGENCES_PAR_ID = {e.id: e for e in EXIGENCES}
