# CreditRisk-Test

Prototype d'API de prédiction du risque de défaut de remboursement, accompagné d'une **stratégie
de test complète** (Évaluation formative n°2, *Tests logiciels* : assurance qualité d'un système
intelligent). Le dépôt contient le système (validation, prétraitement, modèle, API), ses tests
fonctionnels, d'intégration, de robustesse, de non-régression et de performance, la chaîne
GitHub Actions, et les rapports produits.

> **Avertissement.** Le modèle est entraîné sur des **données synthétiques** (`data/DONNEES.md`).
> Il sert à tester le système ; ses métriques **ne démontrent pas** la performance réelle d'un
> modèle de crédit et ne justifient aucune décision d'octroi.

## Arborescence

```
CreditRisk-Test/
├── app/                  # Système : main.py (API), validation.py, preprocessing.py, prediction.py, config.py
├── ml/                   # Données synthétiques, entraînement, métriques, comparaison de versions
├── model/                # Modèle versionné v1.0.0 (.joblib) + métadonnées JSON (empreinte SHA-256)
├── data/                 # Jeux synthétiques figés (entraînement, évaluation) + DONNEES.md
├── scripts/              # Entraînement, comparaison de versions, audit par segments, performance, campagne
├── tests/                # test_validation / test_api / test_integration / test_robustness / test_regression ...
│   └── reference/        # Base de non-régression : baseline, tolérances, cas dorés, contrat d'API
├── reports/              # Rapports produits (traçabilité, anomalies, non-régression, performance)
├── .github/workflows/tests.yml
├── requirements.txt      # Dépendances figées (Python 3.13)
└── README.md
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Lancer l'API

```bash
uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs pour la documentation OpenAPI
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/model-info
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" \
  -d '{"age":35,"revenu_mensuel":250000,"montant_credit":1000000,"duree_mois":12,"anciennete_activite":4}'
```

| Endpoint | Rôle | Réponses |
|---|---|---|
| `GET /health` | Disponibilité du service et du modèle | 200, 503 si le modèle est indisponible |
| `POST /predict` | Probabilité de défaut, niveau de risque, alertes | 200, 400, 413, 415, 422, 500, 503 |
| `GET /model-info` | Version, variables, empreinte SHA-256, métriques de référence | 200, 503 |

Toutes les erreurs ont le même format `{"erreur", "message", "id_requete", "details"?}` ; aucune
trace technique n'est renvoyée au client (le détail est dans le journal, relié par `id_requete`).

## Exécuter les tests

```bash
pytest                                          # toute la suite (quelques secondes)
pytest tests/test_api.py -v                     # un fichier
pytest -m performance                           # tests de performance légers
pytest -k "robustesse or fuzzing"               # sélection par mot-clé
pytest --cov=app --cov=ml --cov-report=term-missing --cov-report=html:reports/htmlcov
pytest --resultats-json=reports/resultats_tests.json   # résultats avec exigences associées
ruff check .                                    # analyse statique
ruff format --check .                           # contrôle du formatage (ruff format . pour corriger)
```

Chaque test est rattaché à une ou plusieurs exigences (`@pytest.mark.exigence("EX01")`) ; la suite
vérifie elle-même que chaque exigence est couverte et que le plan de test cite des tests existants.

## Non-régression du modèle

```bash
python -m scripts.comparer_versions   # compare la référence v1.0.0 à trois candidats
```

La référence (`tests/reference/baseline_v1.0.0.json`), les tolérances (`tolerances.json`) et les
cas dorés (`cas_dores.json`) sont figés dans le dépôt. Verdicts : `CONFORME`, `REVUE_REQUISE`,
`REGRESSION` (rappel ou F1 dégradés au-delà de la tolérance : livraison bloquée).

## Performance

```bash
pip install -r requirements-perf.txt                # Locust et Matplotlib (hors CI)
python -m scripts.benchmark_performance             # latence (P50/P95/P99), rafales, débit saturé (~1,5 min)
python -m scripts.benchmark_performance charge      # charge progressive Locust sur un serveur local (~5,5 min)
python -m scripts.benchmark_performance rapport     # figures et reports/performance/rapport_performance.md
python -m scripts.essai_keep_alive                  # délai d'inactivité keep-alive d'uvicorn (~10 s)
```

Locust à la main (serveur déjà lancé avec `uvicorn app.main:app --port 8000`) :

```bash
locust -f scripts/locustfile.py --headless --host http://127.0.0.1:8000
```

Le profil de charge (paliers de 5 à 700 utilisateurs, arrivées aléatoires, retour à une charge faible)
est défini dans `scripts/locustfile.py` ; il pilote seul la durée de l'essai. Objectifs, méthode,
résultats et interprétation : `reports/performance/rapport_performance.md`.

## Rapports et audits

```bash
python -m scripts.campagne            # plan de test, matrice de traçabilité, résultats des scénarios
python -m scripts.audit_segments      # rappel et faux négatifs par profil de demandeur
```

## GitHub Actions

Le workflow `.github/workflows/tests.yml` s'exécute à chaque Pull Request, à chaque push sur
`main` et à la demande : installation figée, Ruff, Pytest avec couverture (seuil 90 %), archivage
des rapports (`rapports-qualite`).

Publier le dépôt puis vérifier la chaîne :

```bash
git init -b main && git add . && git commit -m "CreditRisk-Test"
git remote add origin https://github.com/<utilisateur>/CreditRisk-Test.git
git push -u origin main
```

**Démontrer qu'un test défaillant fait échouer le workflow** :

- en local : `DEMO_ECHEC=1 pytest tests/test_demo_echec.py` retourne un code de sortie non nul ;
- sur GitHub : onglet *Actions* -> *tests* -> *Run workflow* -> cocher `echec_volontaire` ;
  le job s'arrête en échec (croix rouge). Sur une Pull Request, la fusion est alors bloquée si la
  règle de protection de branche exige ce contrôle.

**Rejouer la chaîne localement, dans un environnement vierge** (installation figée, Ruff, Pytest et
couverture, test volontairement défaillant, défauts injectés un à un dans le code) :

```bash
python -m scripts.preuve_ci --venv-vierge      # environ 4 min ; écrit reports/preuve_ci_locale.md
```

## Régénérer les données et le modèle

```bash
python -m scripts.generer_donnees     # data/*.csv et data/DONNEES.md
python -m scripts.entrainer_modele    # model/*, tests/reference/baseline_*.json et cas_dores.json
```

Ne régénérer le modèle de référence que pour publier une **nouvelle version** (nouveau numéro,
nouvelle baseline, revue des tolérances).

## Limites connues

Pas d'authentification ni de limitation de débit ; données synthétiques ; une seule instance ;
aucune étude d'équité ni de conformité réglementaire. Voir le rapport de qualification.
