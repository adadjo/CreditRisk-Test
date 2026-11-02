"""Style commun des graphiques du dossier de qualification (Matplotlib, surface claire).

Principes : marques fines, grille et axes en filets discrets, une seule teinte quand il n'y a
qu'une série, couleurs catégorielles prises dans l'ordre (bleu, orange, turquoise), texte en
encre neutre (jamais dans la couleur de la série), légende dès deux séries.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
ENCRE = "#0b0b0b"
ENCRE_SECONDAIRE = "#52514e"
ENCRE_ATTENUEE = "#898781"
GRILLE = "#e1e0d9"
AXE = "#c3c2b7"

BLEU, ORANGE, TURQUOISE = "#2a78d6", "#eb6834", "#1baf7a"
RAMPE_BLEUE = ("#86b6ef", "#2a78d6", "#104281")  # rampe ordinale : P50, P95, P99
GRIS_CONTEXTE = ENCRE_ATTENUEE

DPI = 200
LARGEUR = 6.4  # pouces (≈ 16 cm, largeur utile d'une page A4)


def appliquer_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": AXE,
            "axes.linewidth": 0.8,
            "axes.labelcolor": ENCRE_SECONDAIRE,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlecolor": ENCRE,
            "grid.color": GRILLE,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "xtick.color": ENCRE_ATTENUEE,
            "ytick.color": ENCRE_ATTENUEE,
            "xtick.labelcolor": ENCRE_SECONDAIRE,
            "ytick.labelcolor": ENCRE_SECONDAIRE,
            "text.color": ENCRE,
            "font.family": "sans-serif",
            "font.sans-serif": ["Liberation Sans", "Arial", "DejaVu Sans"],
            "font.size": 9,
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "legend.labelcolor": ENCRE_SECONDAIRE,
            "lines.solid_capstyle": "round",
            "lines.solid_joinstyle": "round",
            "savefig.dpi": DPI,
        }
    )


def virgule(valeur: float, decimales: int = 1) -> str:
    """Nombre au format français (virgule décimale)."""
    return f"{valeur:.{decimales}f}".replace(".", ",")


def pourcent(valeur: float, decimales: int = 0) -> str:
    return f"{virgule(100 * valeur, decimales)} %"


def enregistrer(figure, chemin) -> None:
    figure.savefig(chemin, dpi=DPI, bbox_inches="tight", pad_inches=0.12)
    plt.close(figure)
