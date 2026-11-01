"""Cas dorés : demandes représentatives dont la probabilité de référence est figée (non-régression)."""

from __future__ import annotations

CAS_DORES_ENTREES = [
    ("G01", "Profil du sujet (exemple de l'énoncé)", 35, 250_000, 1_000_000, 12, 4),
    ("G02", "Revenu élevé, crédit modeste, longue durée, ancien", 45, 800_000, 1_500_000, 24, 15),
    ("G03", "Revenu moyen, taux d'effort faible, ancienneté solide", 40, 300_000, 900_000, 24, 8),
    ("G04", "Cadre stable, petit crédit court", 52, 600_000, 600_000, 12, 20),
    ("G05", "Taux d'effort modéré, ancienneté moyenne", 33, 200_000, 1_200_000, 12, 5),
    ("G06", "Taux d'effort élevé, ancienneté moyenne", 30, 150_000, 1_500_000, 9, 3),
    ("G07", "Taux d'effort très élevé, courte durée", 28, 120_000, 1_800_000, 6, 2),
    ("G08", "Jeune demandeur, ancienneté nulle, crédit court", 21, 100_000, 600_000, 12, 0),
    ("G09", "Jeune demandeur, ancienneté nulle, durée longue", 22, 110_000, 1_300_000, 36, 0),
    ("G10", "Ancienneté faible, durée 24 mois", 29, 180_000, 2_000_000, 24, 1),
    ("G11", "Ancienneté faible, durée 48 mois", 34, 160_000, 3_000_000, 48, 1),
    ("G12", "Revenu modeste, crédit élevé, 18 mois", 38, 90_000, 1_000_000, 18, 6),
    ("G13", "Âge minimal autorisé", 18, 80_000, 400_000, 12, 0),
    ("G14", "Âge maximal autorisé", 75, 250_000, 800_000, 24, 40),
    (
        "G15",
        "Revenu atypique mais valide (au-dessus du domaine d'entraînement)",
        45,
        8_000_000,
        20_000_000,
        36,
        20,
    ),
    (
        "G16",
        "Crédit atypique mais valide (au-dessus du domaine d'entraînement)",
        40,
        300_000,
        60_000_000,
        60,
        10,
    ),
]


def construire_cas_dores() -> list[dict]:
    """Entrées des cas dorés au format JSON de l'API."""
    return [
        {
            "id": identifiant,
            "description": description,
            "entree": {
                "age": age,
                "revenu_mensuel": revenu,
                "montant_credit": montant,
                "duree_mois": duree,
                "anciennete_activite": anciennete,
            },
        }
        for identifiant, description, age, revenu, montant, duree, anciennete in CAS_DORES_ENTREES
    ]
