# Rapport de non-régression (2026-11-03)

Référence : modèle v1.0.0 ; jeu d'évaluation figé (3000 demandes, 22.5% de défauts) ; seuil de décision 0.3.

## Tolérances (définies avant la comparaison)

| Métrique | Critique | Baisse max. | Hausse max. | Plancher absolu |
|---|---|---|---|---|
| rappel | oui | 0.03 | - | 0.55 |
| f1 | oui | 0.03 | - | - |
| auc_roc | non | 0.02 | - | - |
| precision | non | 0.05 | - | - |
| brier | non | - | 0.01 | - |
| cas dorés (écart de probabilité) | - | 0.05 | - | - |

## Comparaison par métrique

| Métrique | Référence | v1.0.1 (équivalent) | v1.1.0 (amélioré) | v1.2.0 (dégradé) |
|---|---|---|---|---|
| rappel | 0.622 | 0.622 (+0.000) OK | 0.644 (+0.022) OK | 0.538 (-0.084) ECHEC |
| f1 | 0.627 | 0.626 (-0.000) OK | 0.630 (+0.004) OK | 0.601 (-0.026) OK |
| auc_roc | 0.836 | 0.836 (-0.000) OK | 0.843 (+0.007) OK | 0.822 (-0.014) OK |
| precision | 0.632 | 0.631 (-0.001) OK | 0.617 (-0.015) OK | 0.681 (+0.049) OK |
| brier | 0.116 | 0.116 (+0.000) OK | 0.114 (-0.002) OK | 0.135 (+0.019) ECART |

## Verdicts

| Version | Nature | Description | Verdict | Cas dorés hors tolérance | Écart max. | Changements de niveau |
|---|---|---|---|---|---|---|
| v1.0.1 | Équivalent | Régression logistique, régularisation C = 0,5 (au lieu de 1,0) | **CONFORME** | 0/16 | 0.001 | 0 |
| v1.1.0 | Amélioré | Arbre de gradient (modèle non linéaire) | **REVUE_REQUISE** | 5/16 | 0.318 | 1 |
| v1.2.0 | Dégradé | Régression logistique sur-régularisée, C = 0,0005 | **REGRESSION** | 13/16 | 0.370 | 5 |

## Détail des cas dorés hors tolérance

**v1.0.1** : aucun

**v1.1.0** : G02 (+0.082), G04 (+0.087), G09 (+0.318), G12 (-0.059), G14 (+0.052)

**v1.2.0** : G01 (+0.085), G02 (+0.084), G03 (+0.087), G04 (+0.069), G06 (-0.370), G07 (-0.190), G08 (-0.118), G09 (-0.140), G10 (-0.085), G11 (-0.184), G13 (-0.081), G15 (+0.093), G16 (-0.111)

## Non-régression logicielle (code v0.1 -> v0.2)

- Tests réussis : 186 (v0.1) -> 462 (v0.2) ; échecs : 276 -> 0.
- Tests réussis en v0.1 qui échouent en v0.2 : **0**.
- Tests en échec en v0.1 corrigés en v0.2 : 276.
