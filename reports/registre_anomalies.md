# Registre des anomalies

Généré le 2026-11-03 par `python -m scripts.registre_anomalies` à partir des résultats des campagnes (`reports/campagne1_v0.1`, `reports/campagne2_v0.2`), de l'audit par segment et de la mesure de performance.

## Lecture

- **Campagne 1** : code applicatif v0.1.0 (commit 1987160), suite finale de 463 tests : 186 réussis, **276 en échec**, 1 ignoré ; scénarios fonctionnels conformes : 4 sur 27 ; injections de pannes conformes : 0 sur 23 ; fuzzing : 355 erreurs serveur sur 800 requêtes (44,4 %) ; fuite d'information technique dans 13 scénarios sur 27.
- **Campagne 2** : code applicatif v0.2.0, mêmes tests : 462 réussis, **0 en échec**, 1 ignoré, couverture 98,5 % ; scénarios conformes : 27 sur 27 ; pannes conformes : 23 sur 23 ; fuzzing : 0 erreur serveur sur 800 requêtes.
- Les **276 échecs** de la campagne 1 sont rattachés chacun à une seule cause racine (276 rattachés : 275 aux 20 anomalies, 1 au test de fuzzing, symptôme cumulé de A-01, A-02, A-08 et A-10).
- Le code v0.1 est le premier jet volontairement naïf du prototype : les anomalies ci-dessous sont des défauts réels détectés par la stratégie de test, pas des défauts simulés.

## Échelle de gravité

| Gravité | Définition |
| :--- | :--- |
| Critique | résultat invalide ou erroné présenté comme valide, ou modèle non autorisé exécuté, sans aucun signal |
| Majeure | erreur serveur sur une entrée du client, divulgation technique, indisponibilité mal signalée ou donnée invalide acceptée |
| Moyenne | contrat d'API ou de traçabilité non respecté, sans effet direct sur une décision |
| Mineure | écart de forme ou de documentation, sans effet sur le comportement |

## Synthèse par gravité

| Gravité | Anomalies corrigées en v0.2 | Tests en échec en v0.1 | Constats ouverts |
| :--- | ---: | ---: | ---: |
| Critique | 2 | 30 | 2 |
| Majeure | 11 | 213 | 5 |
| Moyenne | 7 | 32 | 2 |
| Mineure | 0 | 0 | 1 |
| **Total** | **20** | **275** | **10** |

## Anomalies détectées en v0.1 et corrigées en v0.2

| Id | Anomalie | Gravité | Exigences | Tests en échec v0.1 | Tests rattachés réussis en v0.2 | Statut |
| :--- | :--- | :--- | :--- | ---: | ---: | :--- |
| A-01 | Entrée incomplète, nulle ou qui n'est pas un objet : erreur 500 au lieu de 422 | Majeure | EX06, EX10, EX11 | 35 | 35 sur 35 | Corrigée |
| A-02 | Valeurs non finies ou démesurées (NaN, Infinity, 1e999, entier géant) : erreur 500 | Majeure | EX02, EX08, EX10 | 40 | 47 sur 47 | Corrigée |
| A-03 | Conversion implicite des types : « 250000 », `true`, « NaN », « Infinity » acceptés comme des nombres | Majeure | EX01, EX02, EX03, EX08, EX12 | 71 | 95 sur 95 | Corrigée |
| A-04 | Troncature silencieuse d'une valeur entière (durée 12,5 mois devient 12) | Moyenne | EX01, EX03 | 4 | 4 sur 4 | Corrigée |
| A-05 | Bornes métier absentes ou incomplètes (montant nul, aucun plafond) | Majeure | EX01, EX02, EX03, EX08, EX12 | 20 | 27 sur 27 | Corrigée |
| A-06 | Schéma non strict : champs supplémentaires, clés dupliquées, casse et alias ignorés ou mal gérés | Moyenne | EX09 | 14 | 14 sur 14 | Corrigée |
| A-07 | Incohérence entre l'âge et l'ancienneté d'activité non contrôlée | Moyenne | EX12 | 5 | 5 sur 5 | Corrigée |
| A-08 | JSON mal formé, corps vide ou octets non décodables : erreur 500 | Majeure | EX10, EX11 | 6 | 6 sur 6 | Corrigée |
| A-09 | Type de contenu non vérifié : un corps `text/plain` est traité | Moyenne | EX10 | 1 | 1 sur 1 | Corrigée |
| A-10 | Aucune limite de taille ni de profondeur : corps volumineux ou très imbriqué provoque une erreur 500 | Majeure | EX10 | 2 | 2 sur 2 | Corrigée |
| A-11 | Erreurs 500 qui exposent la trace, le message de l'exception et des chemins ; pas de code d'erreur distinct | Majeure | EX11 | 2 | 2 sur 2 | Corrigée |
| A-12 | Modèle indisponible mal géré : erreur 500 avec chemin du fichier, `/health` toujours 200, pas de reprise | Majeure | EX05, EX11 | 10 | 10 sur 10 | Corrigée |
| A-13 | Aucun contrôle d'intégrité ni de conformité du modèle chargé | Critique | EX14 | 11 | 11 sur 11 | Corrigée |
| A-14 | Prétraitement sans garde : `log(0)`, division par zéro, variable absente, exceptions brutes | Majeure | EX02, EX06, EX08, EX11 | 12 | 12 sur 12 | Corrigée |
| A-15 | Aucune garde sur le modèle : dimensions incohérentes et probabilités invalides transmises | Critique | EX04, EX11, EX16 | 19 | 19 sur 19 | Corrigée |
| A-16 | Version du modèle codée en dur et incohérente avec les métadonnées (« 1.0 » au lieu de « 1.0.0 ») | Moyenne | EX13, EX14 | 2 | 2 sur 2 | Corrigée |
| A-17 | `/model-info` expose le chemin du fichier du modèle ; les métadonnées internes sont modifiables depuis l'extérieur | Moyenne | EX07, EX11, EX14 | 3 | 3 sur 3 | Corrigée |
| A-18 | Contrat d'API incomplet : 404 et 405 hors format uniforme, schéma de requête absent de l'OpenAPI | Moyenne | EX09, EX10 | 3 | 3 sur 3 | Corrigée |
| A-19 | Seuil de risque élevé mal appliqué : p = 0,60 est classé « modéré » | Majeure | EX16 | 1 | 8 sur 8 | Corrigée |
| A-20 | Alertes « hors domaine d'entraînement » non implémentées (fonction vide) | Majeure | EX04, EX15 | 14 | 14 sur 14 | Corrigée |

### A-01 — Entrée incomplète, nulle ou qui n'est pas un objet : erreur 500 au lieu de 422

- **Gravité** : Majeure — **Exigences** : EX06, EX10, EX11
- **Constat** : Un champ absent ou à `null`, un corps JSON qui est une liste, un texte ou un nombre provoquent une exception non rattrapée (KeyError, TypeError) transformée en erreur 500.
- **Preuves** :
  - scénario S02 « Champ obligatoire absent (revenu_mensuel) » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - scénario S14 « JSON valide mais qui n'est pas un objet (liste) » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - scénario S19 « Objet vide {} » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - scénario S21 « Valeur nulle pour l'âge » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - 35 test(s) en échec sur 35 rattachés en v0.1 ; 35 sur 35 réussis en v0.2
- **Cause racine** : `valider_demande` lit `payload[champ]` sans vérifier la présence du champ ni la forme du corps, et ne rattrape que `ValueError`.
- **Correction** : Validation stricte : le corps doit être un objet, chaque champ est vérifié (présence, type, domaine) et toutes les anomalies sont collectées puis renvoyées ensemble dans un 422 `donnees_invalides`.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-02 — Valeurs non finies ou démesurées (NaN, Infinity, 1e999, entier géant) : erreur 500

- **Gravité** : Majeure — **Exigences** : EX02, EX08, EX10
- **Constat** : Les constantes non standard `NaN`/`Infinity` acceptées par le décodeur JSON de Python, les exposants débordants (`1e999`) et les entiers géants (`10^400`) atteignent le prétraitement ou la conversion en flottant et font échouer la requête (500).
- **Preuves** :
  - scénario S15 « Constante non standard NaN dans le JSON » : attendu 400 json_invalide, observé 500 erreur_interne (avec fuite technique)
  - scénario S16 « Infini obtenu par débordement d'exposant (1e999) » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - scénario S26 « Entier gigantesque (10^400) pour le revenu » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - 40 test(s) en échec sur 47 rattachés en v0.1 ; 47 sur 47 réussis en v0.2
- **Cause racine** : Aucun contrôle de finitude ; `float()` appliqué à un entier géant lève `OverflowError` ; `json.loads` accepte `NaN` et `Infinity` hors norme RFC 8259.
- **Correction** : Rejet des constantes non standard au décodage (400 `json_invalide`), contrôle `math.isfinite`, comparaison aux bornes avant toute conversion (sûre pour un entier géant).
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-03 — Conversion implicite des types : « 250000 », `true`, « NaN », « Infinity » acceptés comme des nombres

- **Gravité** : Majeure — **Exigences** : EX01, EX02, EX03, EX08, EX12
- **Constat** : Une chaîne numérique est convertie sans avertissement, un booléen devient 0 ou 1, des chiffres arabes, la chaîne « NaN » ou la chaîne « Infinity » sont acceptés : une prédiction (ou une erreur 500) est produite à partir d'une donnée qui ne respecte pas le contrat.
- **Preuves** :
  - scénario S05 « Revenu sous forme de chaîne numérique ("250000") » : attendu 422 donnees_invalides, observé 200
  - scénario S20 « Booléen à la place de la durée » : attendu 422 donnees_invalides, observé 200
  - 71 test(s) en échec sur 95 rattachés en v0.1 ; 95 sur 95 réussis en v0.2
- **Cause racine** : `float(payload[champ])` applique les règles de conversion de Python au lieu de contrôler le type JSON reçu.
- **Correction** : Aucune conversion implicite : seul un nombre JSON est accepté, les booléens sont explicitement exclus, le message d'erreur ne reproduit jamais la valeur reçue.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-04 — Troncature silencieuse d'une valeur entière (durée 12,5 mois devient 12)

- **Gravité** : Moyenne — **Exigences** : EX01, EX03
- **Constat** : La durée et l'âge sont tronqués par `int()` : 12,5 mois est traité comme 12 mois, ce qui fausse le taux d'effort sans aucun signal.
- **Preuves** :
  - scénario S08 « Durée de crédit non entière (12,5 mois) » : attendu 422 donnees_invalides, observé 200
  - 4 test(s) en échec sur 4 rattachés en v0.1 ; 4 sur 4 réussis en v0.2
- **Cause racine** : `int(duree)` appliqué après `float()`, sans vérifier que la partie fractionnaire est nulle.
- **Correction** : Une valeur entière attendue doit être un entier ou un flottant entier (35 ou 35.0) ; toute partie fractionnaire non nulle est refusée (`non_entier`).
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-05 — Bornes métier absentes ou incomplètes (montant nul, aucun plafond)

- **Gravité** : Majeure — **Exigences** : EX01, EX02, EX03, EX08, EX12
- **Constat** : Un montant égal à 0 est accepté puis provoque `log(0)` (500) ; aucun plafond n'existe pour le revenu, le montant et l'ancienneté ; les anomalies de plusieurs champs ne sont pas toutes rapportées.
- **Preuves** :
  - scénario S06 « Montant du crédit nul » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - scénario S10 « Valeurs extrêmement élevées sur tous les champs » : attendu 422 donnees_invalides, observé 422 donnees_invalides
  - 20 test(s) en échec sur 27 rattachés en v0.1 ; 27 sur 27 réussis en v0.2
- **Cause racine** : Seuls l'âge, le revenu (> 0) et la durée sont bornés ; le montant n'est refusé que s'il est négatif ; ni plafond ni ancienneté maximale.
- **Correction** : Domaine de validité déclaré pour chaque champ (`config.LIMITES`, bornes incluses) et appliqué à tous ; les anomalies sont cumulées.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-06 — Schéma non strict : champs supplémentaires, clés dupliquées, casse et alias ignorés ou mal gérés

- **Gravité** : Moyenne — **Exigences** : EX09
- **Constat** : Un champ non prévu (par exemple `genre`) est ignoré sans signal ; une clé dupliquée est résolue silencieusement (la dernière gagne) ; `Age` ou un alias anglais sont traités comme des champs manquants (500).
- **Preuves** :
  - scénario S09 « Champ supplémentaire non autorisé (genre) » : attendu 422 donnees_invalides, observé 200
  - scénario S27 « Clé dupliquée dans le JSON (age deux fois, 35 puis -1) » : attendu 400 json_invalide, observé 422 donnees_invalides
  - 14 test(s) en échec sur 14 rattachés en v0.1 ; 14 sur 14 réussis en v0.2
- **Cause racine** : La validation lit les cinq champs attendus et ne regarde jamais les autres clés du corps.
- **Correction** : Schéma strict : tout champ non autorisé est refusé (422 `champ_non_autorise`, noms triés et tronqués) ; une clé dupliquée rend la requête ambiguë (400 `json_invalide`).
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-07 — Incohérence entre l'âge et l'ancienneté d'activité non contrôlée

- **Gravité** : Moyenne — **Exigences** : EX12
- **Constat** : Un demandeur de 20 ans avec 15 ans d'ancienneté est accepté et scoré.
- **Preuves** :
  - scénario S22 « Ancienneté incohérente avec l'âge (20 ans, 15 ans d'activité) » : attendu 422 donnees_invalides, observé 200
  - 5 test(s) en échec sur 5 rattachés en v0.1 ; 5 sur 5 réussis en v0.2
- **Cause racine** : Aucun contrôle inter-champs.
- **Correction** : L'ancienneté ne peut pas dépasser l'âge moins 16 ans (422 `incoherence`).
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-08 — JSON mal formé, corps vide ou octets non décodables : erreur 500

- **Gravité** : Majeure — **Exigences** : EX10, EX11
- **Constat** : Un JSON tronqué, un corps vide ou des octets invalides ne sont pas rattrapés par le gestionnaire de la route et produisent une erreur 500.
- **Preuves** :
  - scénario S12 « Requête mal formée (JSON tronqué) » : attendu 400 json_invalide, observé 500 erreur_interne (avec fuite technique)
  - scénario S13 « Corps de requête vide » : attendu 400 json_invalide, observé 500 erreur_interne (avec fuite technique)
  - 6 test(s) en échec sur 6 rattachés en v0.1 ; 6 sur 6 réussis en v0.2
- **Cause racine** : Le décodage (`request.json()`) est exécuté dans le bloc générique `except Exception` de la route : une erreur de syntaxe devient une erreur 500.
- **Correction** : Toute erreur de décodage devient un 400 `json_invalide` au format d'erreur uniforme.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-09 — Type de contenu non vérifié : un corps `text/plain` est traité

- **Gravité** : Moyenne — **Exigences** : EX10
- **Constat** : Une requête envoyée avec `Content-Type: text/plain` est acceptée et scorée.
- **Preuves** :
  - scénario S17 « Content-Type non JSON (text/plain) » : attendu 415 type_contenu_non_supporte, observé 200
  - 1 test(s) en échec sur 1 rattachés en v0.1 ; 1 sur 1 réussis en v0.2
- **Cause racine** : L'en-tête `Content-Type` n'est pas contrôlé.
- **Correction** : Rejet 415 `type_contenu_non_supporte` si le type n'est pas `application/json`.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-10 — Aucune limite de taille ni de profondeur : corps volumineux ou très imbriqué provoque une erreur 500

- **Gravité** : Majeure — **Exigences** : EX10
- **Constat** : Un corps de 1 Mo ou un JSON imbriqué sur 4 900 niveaux (9,8 Ko) fait échouer la requête (500) : risque de déni de service.
- **Preuves** :
  - scénario S18 « Corps de requête volumineux (1 Mo) » : attendu 413 corps_trop_volumineux, observé 500 erreur_interne (avec fuite technique)
  - scénario S25 « JSON profondément imbriqué (4 900 niveaux, 9,8 Ko) » : attendu 422 donnees_invalides, observé 500 erreur_interne (avec fuite technique)
  - 2 test(s) en échec sur 2 rattachés en v0.1 ; 2 sur 2 réussis en v0.2
- **Cause racine** : Le corps est lu et décodé sans limite ; la récursion du décodeur n'est pas maîtrisée.
- **Correction** : Rejet 413 au-delà de 10 000 octets (annoncés ou réellement lus) ; `RecursionError` traité comme un JSON invalide.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-11 — Erreurs 500 qui exposent la trace, le message de l'exception et des chemins ; pas de code d'erreur distinct

- **Gravité** : Majeure — **Exigences** : EX11
- **Constat** : Les réponses 500 contiennent `message = str(exc)` et la trace complète (chemins de fichiers du serveur, extraits de code, valeurs). Toutes les pannes internes portent le même code `erreur_interne`.
- **Preuves** :
  - injection P-prediction_exception « Erreur interne pendant l'inférence » : attendu 500 erreur_prediction, observé 500 erreur_interne (avec fuite technique)
  - 2 test(s) en échec sur 2 rattachés en v0.1 ; 2 sur 2 réussis en v0.2
- **Cause racine** : Le bloc `except Exception` de la route renvoie `str(exc)` et `traceback.format_exc()` au client.
- **Correction** : Message générique côté client ; le détail est journalisé côté serveur et relié par un identifiant de requête (`id_requete`, `X-Request-ID`) ; codes distincts `erreur_pretraitement`, `erreur_prediction`, `incoherence_dimensions`.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-12 — Modèle indisponible mal géré : erreur 500 avec chemin du fichier, `/health` toujours 200, pas de reprise

- **Gravité** : Majeure — **Exigences** : EX05, EX11
- **Constat** : Si le fichier du modèle ou des métadonnées est absent, illisible ou altéré, `/predict` renvoie une erreur 500 (avec la trace) et `/health` répond 200 « ok ».
- **Preuves** :
  - scénario S11 « Modèle indisponible (non chargé) » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-fichier_absent « Fichier modèle absent » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-octets_aleatoires « Fichier modèle illisible (octets aléatoires) » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-fichier_altere « Fichier modèle altéré (un octet modifié) » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-metadonnees_illisibles « Métadonnées illisibles (JSON invalide) » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-metadonnees_absentes « Fichier de métadonnées absent » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - 10 test(s) en échec sur 10 rattachés en v0.1 ; 10 sur 10 réussis en v0.2
- **Cause racine** : `charger()` laisse remonter les exceptions brutes ; `/health` ne consulte pas l'état du modèle.
- **Correction** : `ModeleIndisponible` unique ; 503 `modele_indisponible` avec `Retry-After` sur les trois endpoints ; `/health` répond 503 ; rechargement automatique à la requête suivante ; une demande invalide reste refusée en 422 même sans modèle.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-13 — Aucun contrôle d'intégrité ni de conformité du modèle chargé

- **Gravité** : Critique — **Exigences** : EX14
- **Constat** : Un modèle substitué, un fichier complété d'octets, une empreinte erronée, un modèle à 5 variables, un objet qui n'est pas un modèle, des métadonnées incomplètes ou aux variables permutées sont chargés et servent des prédictions (200).
- **Preuves** :
  - injection M-objet_non_conforme « Fichier contenant un objet qui n'est pas un modèle » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-modele_a_5_variables « Modèle entraîné sur 5 variables au lieu de 6 » : attendu 503 modele_indisponible, observé 500 erreur_interne (avec fuite technique)
  - injection M-metadonnees_incompletes « Métadonnées incomplètes (clé version absente) » : attendu 503 modele_indisponible, observé 200
  - injection M-variables_divergentes « Variables des métadonnées dans un autre ordre » : attendu 503 modele_indisponible, observé 200
  - injection M-modele_substitue « Autre modèle valide (6 variables) sous le nom du modèle versionné » : attendu 503 modele_indisponible, observé 200
  - injection M-octets_ajoutes « Octets ajoutés en fin de fichier (le fichier reste chargeable) » : attendu 503 modele_indisponible, observé 200
  - injection M-empreinte_metadonnees_erronee « Empreinte SHA-256 des métadonnées erronée » : attendu 503 modele_indisponible, observé 200
  - 11 test(s) en échec sur 11 rattachés en v0.1 ; 11 sur 11 réussis en v0.2
- **Cause racine** : `charger()` désérialise directement le fichier avec `joblib.load` (format pickle, qui exécute du code à la lecture) sans comparer l'empreinte SHA-256 ni vérifier le contrat des métadonnées.
- **Correction** : Contrôles avant désérialisation : métadonnées complètes et variables conformes au prétraitement, empreinte SHA-256 identique ; contrôle du contrat de l'objet chargé (méthodes, nombre de variables, classes). Tout échec produit `ModeleIndisponible`.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-14 — Prétraitement sans garde : `log(0)`, division par zéro, variable absente, exceptions brutes

- **Gravité** : Majeure — **Exigences** : EX02, EX06, EX08, EX11
- **Constat** : Le prétraitement produit silencieusement des infinis ou des NaN (avertissements NumPy) et laisse remonter des exceptions non typées lorsqu'une variable manque.
- **Preuves** :
  - injection P-variable_absente « Variable attendue absente après validation » : attendu 500 erreur_pretraitement, observé 500 erreur_interne (avec fuite technique)
  - injection P-pretraitement_controle « Le prétraitement signale une erreur » : attendu 500 erreur_pretraitement, observé 500 erreur_interne (avec fuite technique)
  - injection P-pretraitement_imprevu « Exception imprévue dans le prétraitement » : attendu 500 erreur_interne, observé 500 erreur_interne (avec fuite technique)
  - 12 test(s) en échec sur 12 rattachés en v0.1 ; 12 sur 12 réussis en v0.2
- **Cause racine** : `ErreurPretraitement` est déclarée mais jamais levée ; aucun contrôle des erreurs flottantes ni de la finitude de la matrice produite.
- **Correction** : Erreurs flottantes transformées en exception (`np.errstate(all='raise')`), vérification de la finitude du résultat, variable absente convertie en `ErreurPretraitement` (500 `erreur_pretraitement`, message générique).
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-15 — Aucune garde sur le modèle : dimensions incohérentes et probabilités invalides transmises

- **Gravité** : Critique — **Exigences** : EX04, EX11, EX16
- **Constat** : Une probabilité de 1,5 ou de -0,1 renvoyée par le modèle est transmise à l'agent de crédit (200) ; NaN et infini produisent une erreur 500 sans corps JSON ; une matrice (2, 6) est acceptée ; (1, 5) et (1, 7) donnent une erreur 500 brute.
- **Preuves** :
  - injection D-1x5 « Dimensions (1, 5) au lieu de (1, 6) » : attendu 500 incoherence_dimensions, observé 500 erreur_interne (avec fuite technique)
  - injection D-1x7 « Dimensions (1, 7) au lieu de (1, 6) » : attendu 500 incoherence_dimensions, observé 500 erreur_interne (avec fuite technique)
  - injection D-2x6 « Dimensions (2, 6) au lieu de (1, 6) » : attendu 500 incoherence_dimensions, observé 200
  - injection P-proba_nan « Le modèle renvoie la probabilité nan » : attendu 500 erreur_prediction, observé 500
  - injection P-proba_1.5 « Le modèle renvoie la probabilité 1.5 » : attendu 500 erreur_prediction, observé 200
  - injection P-proba_-0.1 « Le modèle renvoie la probabilité -0.1 » : attendu 500 erreur_prediction, observé 200
  - injection P-proba_inf « Le modèle renvoie la probabilité inf » : attendu 500 erreur_prediction, observé 500
  - 19 test(s) en échec sur 19 rattachés en v0.1 ; 19 sur 19 réussis en v0.2
- **Cause racine** : `predire` renvoie `float(predict_proba(x)[0, 1])` sans contrôler la forme de l'entrée ni la valeur de la sortie ; `interpreter_probabilite` n'a pas de garde.
- **Correction** : Contrôle de forme et de finitude avant l'inférence (`ErreurDimensions`), contrôle de la probabilité après (finie, dans [0 ; 1]) et garde dans l'interprétation : toute violation devient une erreur 500 générique et journalisée, jamais une probabilité.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-16 — Version du modèle codée en dur et incohérente avec les métadonnées (« 1.0 » au lieu de « 1.0.0 »)

- **Gravité** : Moyenne — **Exigences** : EX13, EX14
- **Constat** : `/predict` annonce la version « 1.0 » alors que le modèle et ses métadonnées sont en 1.0.0 : la réponse n'est pas auditable.
- **Preuves** :
  - 2 test(s) en échec sur 2 rattachés en v0.1 ; 2 sur 2 réussis en v0.2
- **Cause racine** : Constante de version dans le code de l'API.
- **Correction** : La version annoncée est lue dans les métadonnées du modèle réellement chargé.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-17 — `/model-info` expose le chemin du fichier du modèle ; les métadonnées internes sont modifiables depuis l'extérieur

- **Gravité** : Moyenne — **Exigences** : EX07, EX11, EX14
- **Constat** : La réponse contient `chemin_modele` (chemin absolu du fichier sur le serveur) ; la propriété `metadonnees` du service renvoie l'objet interne et non une copie : un appelant peut falsifier les métadonnées du service.
- **Preuves** :
  - 3 test(s) en échec sur 3 rattachés en v0.1 ; 3 sur 3 réussis en v0.2
- **Cause racine** : La réponse reprend `str(service.chemin_modele)` et la propriété `metadonnees` expose l'objet interne.
- **Correction** : Liste blanche de champs exposés (version, variables, empreinte, métriques de référence, seuils), sans chemin ; copie profonde des métadonnées.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-18 — Contrat d'API incomplet : 404 et 405 hors format uniforme, schéma de requête absent de l'OpenAPI

- **Gravité** : Moyenne — **Exigences** : EX09, EX10
- **Constat** : Les erreurs 404 et 405 reprennent le format par défaut du framework ; la documentation OpenAPI ne décrit ni le corps de requête ni les erreurs.
- **Preuves** :
  - scénario S23 « Méthode non autorisée (GET /predict) » : attendu 405 methode_non_autorisee, observé 405
  - scénario S24 « Ressource inconnue (GET /inconnu) » : attendu 404 ressource_introuvable, observé 404
  - 3 test(s) en échec sur 3 rattachés en v0.1 ; 3 sur 3 réussis en v0.2
- **Cause racine** : Gestionnaires d'erreurs HTTP par défaut ; route sans modèle de requête déclaré.
- **Correction** : Gestionnaire d'exceptions HTTP au format uniforme (`ressource_introuvable`, `methode_non_autorisee`) ; schéma de requête et codes d'erreur documentés dans l'OpenAPI.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-19 — Seuil de risque élevé mal appliqué : p = 0,60 est classé « modéré »

- **Gravité** : Majeure — **Exigences** : EX16
- **Constat** : La règle attendue est p ≥ 0,60 → « élevé » ; le code compare avec `<=`.
- **Preuves** :
  - 1 test(s) en échec sur 8 rattachés en v0.1 ; 8 sur 8 réussis en v0.2
- **Cause racine** : Opérateur de comparaison `<=` au lieu de `<` à la borne.
- **Correction** : `p < 0,30` faible ; `0,30 ≤ p < 0,60` modéré ; `p ≥ 0,60` élevé, avec tests aux bornes (0, 0,2999, 0,30, 0,5999, 0,60, 1).
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### A-20 — Alertes « hors domaine d'entraînement » non implémentées (fonction vide)

- **Gravité** : Majeure — **Exigences** : EX04, EX15
- **Constat** : Une demande valide mais très éloignée des données d'entraînement (revenu de 20 millions, montant de 200 millions, durée de 120 mois…) est scorée sans aucun avertissement : fausse confiance dans une extrapolation.
- **Preuves** :
  - 14 test(s) en échec sur 14 rattachés en v0.1 ; 14 sur 14 réussis en v0.2
- **Cause racine** : `evaluer_alertes` renvoie une liste vide (marquée TODO).
- **Correction** : Comparaison de chaque champ et du taux d'effort au domaine observé à l'entraînement (métadonnées du modèle) ; alerte `hors_domaine_entrainement` portée par la réponse 200.
- **Statut** : Corrigée en v0.2, vérifiée par la campagne 2

### T-00 — Symptôme transversal (fuzzing)

- Symptôme transversal : le fuzzing de 800 requêtes ne doit produire aucune erreur serveur : v0.1 : 355 erreurs serveur sur 800 requêtes (statuts : {"200": 138, "422": 307, "500": 355}) ; v0.2 : 0 (statuts : {"200": 62, "400": 146, "422": 592}). Cumul des causes A-01, A-02, A-08 et A-10 : aucun défaut propre.

## Constats ouverts (non corrigés par le prototype)

Ces constats ne sont pas des défauts de code corrigeables par une retouche : ils relèvent de décisions métier, de conception ou de gouvernance. Ils conditionnent la conclusion sur la mise en production.

| Id | Constat | Gravité | Statut |
| :--- | :--- | :--- | :--- |
| O-01 | Taux de faux négatifs très élevé sur des profils précis, invisible dans les indicateurs globaux | Critique | Ouvert |
| O-02 | Extrapolation hors du domaine d'entraînement : probabilités extrêmes ou trompeuses malgré l'alerte | Majeure | Ouvert |
| O-03 | Aucune authentification, aucun chiffrement de transport, aucune limitation de débit | Majeure | Ouvert |
| O-04 | Chargement du modèle par pickle : l'empreinte protège contre l'erreur, pas contre un attaquant qui écrit les deux fichiers | Majeure | Ouvert |
| O-05 | Aucune analyse d'équité ni de conformité réglementaire ; l'âge est une variable explicative | Majeure | Ouvert |
| O-06 | Données exclusivement synthétiques : aucune conclusion sur la performance réelle | Critique | Ouvert |
| O-07 | Exploitation : instance unique, aucune supervision de la dérive ni de la performance en production | Moyenne | Ouvert |
| O-08 | Rares échecs de connexion persistante (statut 0) sous charge soutenue | Mineure | Ouvert |
| O-09 | Message de recommandation « Profil standard : poursuivre l'instruction habituelle » au niveau faible | Majeure | Ouvert |
| O-10 | Seuils de risque 0,30 et 0,60 non validés par le métier | Moyenne | Ouvert |

### O-01 — Taux de faux négatifs très élevé sur des profils précis, invisible dans les indicateurs globaux

- **Gravité** : Critique — **Exigences** : EX07, EX16
- **Constat** : Au seuil de décision 0,30, le rappel global est de 0,622 (faux négatifs : 37,8 %), avec une AUC de 0,836 et une erreur de calibration de 0,018. Pour les prêts de 24 mois ou plus (n = 1 072, 135 défauts), le rappel tombe à 0,207 (faux négatifs : 79,3 %) ; pour les demandeurs de moins de 2 ans d'ancienneté avec un prêt de 24 mois ou plus (n = 116, 48 défauts), il est de 0,167 (40 défauts sur 48 non signalés). Tous les tests fonctionnels et de non-régression passent.
- **Preuve** : reports/audit_segments.md (données synthétiques ; l'interaction durée × ancienneté a été introduite volontairement dans le générateur pour que l'audit ait quelque chose à trouver)
- **Suite** : Ouvert : décision métier. Pistes : seuil adapté ou revue manuelle obligatoire pour les prêts de 24 mois ou plus (au seuil 0,20 le rappel global passe à 0,727 et à 0,356 pour les prêts longs, avec 32,7 % de dossiers signalés ; au seuil 0,10 : 0,917 et 0,815, mais 64,2 % de dossiers signalés), critères d'acceptation par segment dans la non-régression, réentraînement avec interaction ou modèle non linéaire.

### O-02 — Extrapolation hors du domaine d'entraînement : probabilités extrêmes ou trompeuses malgré l'alerte

- **Gravité** : Majeure — **Exigences** : EX15
- **Constat** : Le cas doré G16 (montant de 60 millions, hors du domaine d'entraînement) obtient une probabilité de défaut de 0,99998 ; le cas G15 (revenu de 8 millions) obtient 0,0081. L'alerte `hors_domaine_entrainement` est émise, mais la probabilité reste renvoyée comme les autres.
- **Preuve** : tests/reference/cas_dores.json (G15, G16), tests de robustesse EX15
- **Suite** : Ouvert : décider si une demande hors domaine doit être orientée vers une revue manuelle sans score affiché.

### O-03 — Aucune authentification, aucun chiffrement de transport, aucune limitation de débit

- **Gravité** : Majeure — **Exigences** : EX10, EX11
- **Constat** : L'API est ouverte : tout client qui l'atteint peut interroger `/predict` et `/model-info`, sans trace d'audit des décisions ni limite de débit.
- **Preuve** : Conception du prototype (hors périmètre de la consigne)
- **Suite** : Ouvert : à traiter avant tout déploiement (authentification, TLS, quota, journal d'audit sans donnée personnelle superflue).

### O-04 — Chargement du modèle par pickle : l'empreinte protège contre l'erreur, pas contre un attaquant qui écrit les deux fichiers

- **Gravité** : Majeure — **Exigences** : EX14
- **Constat** : Le contrôle SHA-256 détecte une corruption ou une substitution accidentelle et empêche de désérialiser un fichier inattendu, mais l'empreinte attendue est stockée à côté du modèle.
- **Preuve** : tests TC14 et TC15 ; app/prediction.py
- **Suite** : Ouvert : signer le modèle ou publier l'empreinte par un canal distinct, restreindre les droits d'écriture, envisager un format sans exécution de code.

### O-05 — Aucune analyse d'équité ni de conformité réglementaire ; l'âge est une variable explicative

- **Gravité** : Majeure
- **Constat** : Les écarts de performance entre groupes (âge, genre, zone) ne sont ni mesurés ni encadrés ; l'usage de l'âge dans un modèle de crédit peut être restreint selon le cadre juridique applicable.
- **Preuve** : Hors périmètre des tests ; audit limité aux segments d'âge, d'ancienneté, de revenu et de durée
- **Suite** : Ouvert : analyse d'impact et d'équité par la conformité avant tout usage décisionnel.

### O-06 — Données exclusivement synthétiques : aucune conclusion sur la performance réelle

- **Gravité** : Critique
- **Constat** : Le jeu d'entraînement et le jeu d'évaluation sont générés par un modèle probabiliste écrit pour l'exercice ; les métriques mesurent la cohérence du système, pas la qualité d'un score de crédit.
- **Preuve** : data/DONNEES.md
- **Suite** : Ouvert : le modèle doit être requalifié (mêmes tests, baseline, audit par segment) sur des données réelles, anonymisées et représentatives.

### O-07 — Exploitation : instance unique, aucune supervision de la dérive ni de la performance en production

- **Gravité** : Moyenne — **Exigences** : EX05, EX17
- **Constat** : Un seul processus sert l'API ; rien ne surveille la distribution des entrées, la calibration ou le rappel par segment une fois en service.
- **Preuve** : Architecture du prototype
- **Suite** : Ouvert : redondance, métriques d'exploitation, suivi de dérive et de calibration, procédure de retour arrière documentée.

### O-08 — Rares échecs de connexion persistante (statut 0) sous charge soutenue

- **Gravité** : Mineure — **Exigences** : EX17
- **Constat** : Lors d'un des deux essais de charge progressive, 4 requêtes sur 73 860 ont échoué sans réponse ; l'essai final n'en compte aucun sur 73 632. Cause reproduite de façon déterministe : fermeture de la connexion inactive par uvicorn au bout de 5 s (`--timeout-keep-alive`) au moment où le client la réutilise.
- **Preuve** : reports/performance/essai_keep_alive.txt
- **Suite** : Atténuation documentée : aligner les délais (client plus court que le serveur) ou placer un reverse proxy ; nouvelle tentative côté client pour les requêtes idempotentes.

### O-09 — Message de recommandation « Profil standard : poursuivre l'instruction habituelle » au niveau faible

- **Gravité** : Majeure — **Exigences** : EX16
- **Constat** : Un niveau « faible » est présenté comme un profil standard à instruire normalement, alors que le modèle laisse passer une part importante de défauts dans certains segments (O-01) : le texte rassure plus que ce que les preuves permettent.
- **Preuve** : app/prediction.py (`interpreter_probabilite`)
- **Suite** : Ouvert : reformuler (« aucun signal de risque élevé détecté par le modèle ; ne dispense pas de l'analyse habituelle ») après validation par le métier.

### O-10 — Seuils de risque 0,30 et 0,60 non validés par le métier

- **Gravité** : Moyenne — **Exigences** : EX16
- **Constat** : Les seuils sont des hypothèses de conception du prototype (l'énoncé n'en fixe aucun) ; aucune analyse de coût (crédit accordé à tort, dossier refusé à tort, charge de revue) ne les justifie.
- **Preuve** : reports/audit_segments.md (balayage de seuils)
- **Suite** : Ouvert : décision métier fondée sur le balayage de seuils et la capacité de revue.

## Lacune de la suite de tests découverte par injection de défauts

### T-01 — Lacune de la suite de tests : la désactivation du contrôle SHA-256 n'était détectée par aucun test

- **Gravité** : Majeure — **Exigences** : EX14
- **Constat** : L'injection de défauts dans le code (`scripts/preuve_ci.py`, mutant M4 : contrôle d'empreinte remplacé par `if False`) laissait la suite entièrement verte : le défaut « fichier altéré » échouait par un autre chemin (le fichier modifié n'était plus chargeable) et masquait l'absence de contrôle.
- **Suite** : Corrigée : trois défauts silencieux (modèle substitué, octets ajoutés, empreinte des métadonnées erronée), un test exigeant que le fichier suspect ne soit jamais désérialisé et un témoin positif (cas de test TC15). Les 15 défauts injectés sont désormais tous détectés (reports/preuve_ci_locale.md).
