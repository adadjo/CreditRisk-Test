# Preuve d'exécution de la chaîne d'intégration continue (réplication locale)

Générée le 2026-11-02 18:23 UTC par `python -m scripts.preuve_ci`.

> Ce document prouve que les commandes du workflow `.github/workflows/tests.yml` réussissent dans un environnement vierge et qu'elles échouent quand un test échoue. **L'exécution sur GitHub (runner `ubuntu-latest`) reste à réaliser après la publication du dépôt** : voir la section « Publier le dépôt » du README. L'URL du dépôt et celle de l'exécution doivent être ajoutées au rapport final.

## 1. Environnement

- Python 3.13.18 (Linux 6.18.44-fc-v185)
- Outils : pytest==9.1.1, pytest-cov==7.1.0, ruff==0.17.3
- Environnement virtuel créé pour l'occasion, dépendances installées depuis `requirements.txt` (versions figées), comme sur un runner vierge.

## 2. Chaîne nominale : tout doit réussir

| Étape | Commande | Code de sortie | Durée (s) | Verdict |
| :--- | :--- | ---: | ---: | :--- |
| 0. Installation des dépendances figées | `pip install -r requirements.txt` | 0 | 21,3 | **réussie** |
| 1. Analyse statique | `ruff check .` | 0 | 0,4 | **réussie** |
| 2. Formatage | `ruff format --check .` | 0 | 0,0 | **réussie** |
| 3. Tests et couverture (seuil 90 %) | `pytest --cov=app --cov=ml --cov-fail-under=90 --junitxml=… --resultats-json=…` | 0 | 18,7 | **réussie** |

Bilan de pytest : `462 passed, 1 skipped in 12.37s` ; couverture totale : **98,50 %** ; Required test coverage of 90% reached. Total coverage: 98.50%.

Ruff est lancé avec `--no-cache` (aucun cache local), comme sur un runner vierge.

```text
All checks passed!
41 files already formatted
------------------------------------------------------------------
TOTAL                    547      5    120      5    99%
Coverage HTML written to dir reports/_tmp/ci_nominal/htmlcov
Coverage XML written to file reports/_tmp/ci_nominal/coverage.xml
Required test coverage of 90% reached. Total coverage: 98.50%
=========================== short test summary info ============================
SKIPPED [1] tests/test_demo_echec.py:14: actif seulement avec DEMO_ECHEC=1
======================= 462 passed, 1 skipped in 12.37s ========================
```

Couverture par module (pytest-cov, branches comprises) :

```text
Name                   Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------
app/__init__.py            0      0      0      0   100%
app/config.py             18      0      0      0   100%
app/main.py              116      2     10      0    98%   212-213
app/prediction.py        116      2     32      2    97%   116, 122
app/preprocessing.py      21      0      2      0   100%
app/validation.py         88      1     40      1    98%   64
ml/__init__.py             0      0      0      0   100%
ml/cas_dores.py            4      0      0      0   100%
ml/comparaison.py         53      0     16      0   100%
ml/donnees.py             40      0      2      0   100%
ml/entrainement.py        47      0      4      0   100%
ml/evaluation.py          44      0     14      2    97%   101->107, 105->103
------------------------------------------------------------------
TOTAL                    547      5    120      5    99%
```

## 3. Un test défaillant bloque la chaîne

Même commande que l'étape 3, avec `DEMO_ECHEC=1` (variable positionnée par le déclenchement manuel du workflow, entrée `echec_volontaire`). Les rapports sont écrits dans un dossier temporaire pour ne pas écraser ceux de l'étape 3.

| Commande | Code de sortie | Bilan | Test en échec | Verdict |
| :--- | ---: | :--- | :--- | :--- |
| `DEMO_ECHEC=1 pytest --cov=app --cov=ml --cov-fail-under=90 …` | 1 | `1 failed, 462 passed in 13.59s` | `tests/test_demo_echec.py::test_echec_volontaire_pour_verifier_que_la_ci_bloque` | **le workflow échouerait (code ≠ 0)** |

```text
ml/__init__.py             0      0      0      0   100%
ml/cas_dores.py            4      0      0      0   100%
ml/comparaison.py         53      0     16      0   100%
ml/donnees.py             40      0      2      0   100%
ml/entrainement.py        47      0      4      0   100%
ml/evaluation.py          44      0     14      2    97%   101->107, 105->103
------------------------------------------------------------------
TOTAL                    547      5    120      5    99%
Coverage HTML written to dir reports/_tmp/ci_echec_volontaire/htmlcov
Coverage XML written to file reports/_tmp/ci_echec_volontaire/coverage.xml
Required test coverage of 90% reached. Total coverage: 98.50%
=========================== short test summary info ============================
FAILED tests/test_demo_echec.py::test_echec_volontaire_pour_verifier_que_la_ci_bloque
======================== 1 failed, 462 passed in 13.59s ========================
```

## 4. Un défaut introduit dans le code est détecté

Chaque défaut est injecté seul dans une copie temporaire du dépôt ; la suite de tests est ensuite exécutée telle quelle. Une Pull Request contenant ce changement serait bloquée.

| Id | Défaut injecté | Fichier | Code de sortie | Tests en échec | Verdict |
| :--- | :--- | :--- | ---: | ---: | :--- |
| M1 | Seuil de risque élevé : `p < 0,60` devient `p <= 0,60` (défaut observé en v0.1) | `app/prediction.py` | 1 | 1 | **détecté** |
| M2 | Borne minimale d'un champ exclue : `minimum <= valeur` devient `minimum < valeur` | `app/validation.py` | 1 | 33 | **détecté** |
| M3 | Garde de plage supprimée : une probabilité hors de [0, 1] n'est plus refusée | `app/prediction.py` | 1 | 3 | **détecté** |
| M4 | Contrôle d'intégrité SHA-256 du modèle désactivé | `app/prediction.py` | 1 | 7 | **détecté** |
| M5 | Les booléens sont acceptés comme des nombres (`true` -> 1) | `app/validation.py` | 1 | 16 | **détecté** |
| M6 | Contrôle des valeurs non finies (infini issu de `1e999`) supprimé | `app/validation.py` | 1 | 22 | **détecté** |
| M7 | Cohérence âge / ancienneté : `>` devient `>=` (un cas limite valide est refusé) | `app/validation.py` | 1 | 7 | **détecté** |
| M8 | Taux d'effort mal calculé : `montant / durée` devient `montant * durée` | `app/preprocessing.py` | 1 | 25 | **détecté** |
| M9 | Colonnes `log_revenu` et `log_montant` permutées (décalage entraînement / service) | `app/preprocessing.py` | 1 | 19 | **détecté** |
| M10 | L'en-tête `Retry-After` n'est plus envoyé avec le 503 | `app/main.py` | 1 | 1 | **détecté** |
| M11 | Contrôle du Content-Type supprimé (plus de 415) | `app/main.py` | 1 | 1 | **détecté** |
| M12 | Taille maximale du corps de requête portée de 10 000 octets à 10 Mo | `app/config.py` | 1 | 1 | **détecté** |
| M13 | L'identifiant de requête n'est plus renvoyé dans l'en-tête `X-Request-ID` | `app/main.py` | 1 | 29 | **détecté** |
| M14 | Seuil de risque modéré modifié : 0,30 devient 0,35 | `app/config.py` | 1 | 6 | **détecté** |
| M15 | Contrôle de conformité du modèle chargé : nombre de variables ignoré | `app/prediction.py` | 1 | 1 | **détecté** |

- M1 : 1 failed, 461 passed, 1 skipped in 8.08s ; par exemple `test_niveaux_de_risque_aux_bornes[0.6-eleve]`.
- M2 : 33 failed, 429 passed, 1 skipped in 7.82s ; par exemple `test_probabilite_valide_sur_demandes_variees[age_min]`, `test_probabilite_valide_sur_demandes_variees[duree_min]`, `test_probabilite_valide_sur_demandes_variees[revenu_min]`, `test_probabilite_valide_sur_demandes_variees[extremes]`.
- M3 : 3 failed, 459 passed, 1 skipped in 8.41s ; par exemple `test_probabilite_invalide_du_modele_jamais_transmise[negative]`, `test_probabilite_invalide_du_modele_jamais_transmise[superieure_a_1]`, `test_probabilite_invalide_du_modele_jamais_transmise[deux]`.
- M4 : 7 failed, 455 passed, 1 skipped in 7.37s ; par exemple `test_modele_non_chargeable_est_signale_proprement[modele_substitue]`, `test_modele_non_chargeable_est_signale_proprement[octets_ajoutes]`, `test_modele_non_chargeable_est_signale_proprement[empreinte_metadonnees_erronee]`, `test_empreinte_non_conforme_refuse_le_modele_sans_le_deserialiser[fichier_altere]`.
- M5 : 16 failed, 446 passed, 1 skipped in 7.55s ; par exemple `test_scenarios_api[S20]`, `test_valeurs_non_numeriques[bool-True-age]`, `test_valeurs_non_numeriques[bool-True-revenu_mensuel]`, `test_valeurs_non_numeriques[bool-True-montant_credit]`.
- M6 : 22 failed, 440 passed, 1 skipped in 9.20s ; par exemple `test_scenarios_api[S16]`, `test_infinis_par_debordement_refuses[1e999-age]`, `test_infinis_par_debordement_refuses[1e999-revenu_mensuel]`, `test_infinis_par_debordement_refuses[1e999-montant_credit]`.
- M7 : 7 failed, 455 passed, 1 skipped in 8.61s ; par exemple `test_toutes_les_lignes_synthetiques_sont_des_demandes_valides`, `test_limites_incluses_acceptees[anciennete_activite]`, `test_entrees_atypiques_valides_signalees[anciennete_59]`, `test_entrees_atypiques_valides_signalees[tout_extreme]`.
- M8 : 25 failed, 437 passed, 1 skipped in 7.98s ; par exemple `test_pipeline_de_bout_en_bout_et_metadonnees_coherentes`, `test_metriques_du_modele_courant_conformes_a_la_reference`, `test_candidat_equivalent_est_conforme`, `test_cas_dores_identiques_a_la_reference`.
- M9 : 19 failed, 443 passed, 1 skipped in 8.25s ; par exemple `test_metriques_du_modele_courant_conformes_a_la_reference`, `test_cas_dores_identiques_a_la_reference`, `test_cas_dores_via_l_api[G01]`, `test_cas_dores_via_l_api[G02]`.
- M10 : 1 failed, 461 passed, 1 skipped in 8.49s ; par exemple `test_scenarios_api[S11]`.
- M11 : 1 failed, 461 passed, 1 skipped in 8.04s ; par exemple `test_scenarios_api[S17]`.
- M12 : 1 failed, 461 passed, 1 skipped in 7.29s ; par exemple `test_scenarios_api[S18]`.
- M13 : 29 failed, 433 passed, 1 skipped in 7.35s ; par exemple `test_scenarios_api[S01]`, `test_scenarios_api[S02]`, `test_scenarios_api[S03]`, `test_scenarios_api[S04]`.
- M14 : 6 failed, 456 passed, 1 skipped in 7.62s ; par exemple `test_model_info_contrat`, `test_metriques_du_modele_courant_conformes_a_la_reference`, `test_candidat_equivalent_est_conforme`, `test_candidat_ameliore_n_est_pas_une_regression`.
- M15 : 1 failed, 461 passed, 1 skipped in 7.14s ; par exemple `test_modele_non_chargeable_est_signale_proprement[modele_a_5_variables]`.

## 5. Contrôle statique du workflow

```json
{
 "declencheurs": [
  "pull_request",
  "push",
  "workflow_dispatch"
 ],
 "runner": "ubuntu-latest",
 "python": "3.13",
 "etapes": [
  "Récupérer le code",
  "Installer Python",
  "Installer les dépendances figées",
  "Ruff - analyse statique",
  "Ruff - formatage",
  "Pytest avec couverture",
  "Archiver les rapports"
 ],
 "ruff_check": true,
 "ruff_format": true,
 "pytest": true,
 "couverture_seuil_90": true,
 "rapports_toujours_archives": true,
 "demo_echec_declenchable": true
}
```

## Ce qui reste à faire par l'étudiant

1. Créer le dépôt GitHub `CreditRisk-Test`, pousser le code (README, section « Publier le dépôt »).
2. Ouvrir une Pull Request : le workflow doit réussir (coche verte).
3. Déclencher manuellement le workflow avec `echec_volontaire = true` : il doit échouer (croix rouge).
4. Reporter dans le rapport final l'URL du dépôt et celles des deux exécutions (captures d'écran).
