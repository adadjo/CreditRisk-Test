# Données synthétiques du prototype

> **Avertissement.** Ces données sont **synthétiques** : elles ont été générées par un programme
> (`ml/donnees.py`) pour **tester le système**. Elles ne reflètent aucune clientèle réelle et
> **ne permettent pas de démontrer la performance réelle d'un modèle de crédit**. Les métriques
> du modèle de référence n'ont de valeur que comme *point de comparaison* pour la non-régression.

## Fichiers

| Fichier | Lignes | Taux de défaut | SHA-256 |
|---|---:|---:|---|
| `data/jeu_entrainement.csv` | 9000 | 22.5% | `2e439d642856c8c3c8aebf8d76fc8a17f3df3521ec4a9f7008e14d7c5df2b2d6` |
| `data/jeu_evaluation.csv` | 3000 | 22.5% | `321d84c477b6cf972533b0c92dda1ed9c67bca0cbc79fc41295ec5aca960d7ea` |

Le jeu d'évaluation est **figé** : toutes les comparaisons de versions s'appuient sur lui.
Régénération (identique à l'octet près pour une même version de NumPy) :
`python -m scripts.generer_donnees`.

## Variables

| Variable | Description | Unité | Génération |
|---|---|---|---|
| `age` | Âge du demandeur | ans | loi normale (moyenne 38, écart-type 10), bornée à [18 ; 70] |
| `revenu_mensuel` | Revenu mensuel | FCFA | log-normale (médiane 180 000), arrondie au millier, bornée à [40 000 ; 3 000 000] |
| `montant_credit` | Montant demandé | FCFA | revenu x multiple log-normal (médiane 5), arrondi à 10 000, borné à [50 000 ; 20 000 000] |
| `duree_mois` | Durée du crédit | mois | tirage parmi 6, 9, 12, 18, 24, 36, 48 (12 mois le plus fréquent) |
| `anciennete_activite` | Ancienneté de l'activité | ans | loi gamma (moyenne 5), entière, plafonnée à `age - 16` |
| `defaut` | Cible : 1 = défaut, 0 = remboursement sans défaut | - | tirage de Bernoulli sur le risque ci-dessous |

## Mécanisme de la cible

Le logit du risque est la somme de : une constante (calibrée pour environ 22 % de défauts), un effet
croissant du **taux d'effort** (mensualité estimée / revenu), un effet décroissant de l'**ancienneté**,
un surrisque pour les **moins de 25 ans**, un léger effet de la durée, un **bruit gaussien** (facteurs
non observés) et une **interaction cachée** : un surrisque marqué quand l'ancienneté est inférieure à
2 ans **et** la durée supérieure ou égale à 24 mois.

Cette interaction est **volontaire** : le modèle de référence est linéaire et ne peut pas l'apprendre.
Elle crée un segment dont le taux de faux négatifs est élevé, ce qui permet de démontrer l'audit par
segments et de répondre à la question de synthèse de l'évaluation avec des mesures plutôt que des
hypothèses.

## Hypothèses simplificatrices

- La mensualité est estimée sans intérêts (`montant / durée`).
- Aucune variable sensible (genre, ethnie, religion) n'est présente ; l'âge reste une variable
  potentiellement discriminante dont l'usage doit être validé par la conformité.
- La définition de « défaut » est abstraite (1 = non-remboursement) ; aucune notion de retard de
  paiement, de restructuration ni de recouvrement n'est modélisée.
