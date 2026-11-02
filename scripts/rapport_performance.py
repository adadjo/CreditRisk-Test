"""Rapport de performance : figures et document Markdown à partir de performance.json.

Usage : python -m scripts.benchmark_performance rapport
(les mesures doivent avoir été produites avant par les sous-commandes `mesurer` et `charge`).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from scripts.style_graphiques import (
    AXE,
    BLEU,
    ENCRE,
    ENCRE_ATTENUEE,
    ENCRE_SECONDAIRE,
    LARGEUR,
    ORANGE,
    RAMPE_BLEUE,
    SURFACE,
    appliquer_style,
    enregistrer,
    virgule,
)

# Hypothèses de dimensionnement (à confirmer avec le métier) : voir « Objectifs » dans le rapport.
HYPOTHESES = {"agents": 300, "intervalle_s": 15, "marge": 2.5}


# --------------------------------------------------------------------------------------------
# Mise en forme
# --------------------------------------------------------------------------------------------


def nombre(valeur, decimales: int = 1) -> str:
    return "—" if valeur is None else virgule(float(valeur), decimales)


def entier(valeur) -> str:
    return "—" if valeur is None else f"{int(round(valeur)):,}".replace(",", " ")


def tableau(entetes: list[str], lignes: list[list[str]], droite: set[int] | None = None) -> str:
    droite = droite or set()
    separateurs = ["---:" if i in droite else ":---" for i in range(len(entetes))]
    corps = ["| " + " | ".join(ligne) + " |" for ligne in lignes]
    return "\n".join(
        ["| " + " | ".join(entetes) + " |", "| " + " | ".join(separateurs) + " |", *corps]
    )


# --------------------------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------------------------


def evaluer_objectifs(d: dict) -> list[dict]:
    """Compare chaque objectif à la mesure correspondante."""
    o, m, c = d["objectifs"], d["micro_mesures"], d["charge"]
    inference = m["inference_service"]["p95_ms"]
    api = m["api_http_local"]["p95_ms"]
    conforme = c["dernier_palier_conforme"] or {"debit_observe_req_s": 0, "cible_req_s": 0}
    essai1 = d.get("charge_essai_precedent") or {}
    conforme1 = essai1.get("dernier_palier_conforme") or conforme
    pire_debit = min(conforme["debit_observe_req_s"], conforme1["debit_observe_req_s"])
    mesure_debit = f"{nombre(conforme['debit_observe_req_s'], 0)} req/s"
    if essai1:
        mesure_debit += (
            f" (essai 2) ; {nombre(conforme1['debit_observe_req_s'], 0)} req/s (essai 1)"
        )
    rec = c["recuperation"]
    erreurs = c["erreurs_journal_serveur"]
    disponible = (
        c["sante_apres_charge"] == 200 and erreurs["traceback"] == 0 and erreurs["statuts_5xx"] == 0
    )
    return [
        {
            "id": "O1",
            "indicateur": "Latence d'inférence du modèle, P95",
            "objectif": f"≤ {nombre(o['p95_inference_ms'], 0)} ms",
            "mesure": f"{nombre(inference, 2)} ms",
            "respecte": inference <= o["p95_inference_ms"],
            "marge": f"× {nombre(o['p95_inference_ms'] / inference, 0)}",
            "marge_num": o["p95_inference_ms"] / inference,
        },
        {
            "id": "O2",
            "indicateur": "Temps de réponse de l'API, P95 (requêtes valides, client unique)",
            "objectif": f"≤ {nombre(o['p95_api_ms'], 0)} ms",
            "mesure": f"{nombre(api, 2)} ms",
            "respecte": api <= o["p95_api_ms"],
            "marge": f"× {nombre(o['p95_api_ms'] / api, 0)}",
            "marge_num": o["p95_api_ms"] / api,
        },
        {
            "id": "O3",
            "indicateur": "Débit soutenu avec P95 ≤ 200 ms et aucun échec",
            "objectif": f"≥ {nombre(o['debit_min_req_s'], 0)} req/s",
            "mesure": mesure_debit,
            "respecte": pire_debit >= o["debit_min_req_s"],
            "marge": f"× {nombre(pire_debit / o['debit_min_req_s'], 1)}",
            "marge_num": pire_debit / o["debit_min_req_s"],
        },
        {
            "id": "O4",
            "indicateur": "Disponibilité après surcharge et retour au niveau initial",
            "objectif": f"aucune erreur serveur ; P95 final ≤ {nombre(o['recuperation_p95_max_facteur'], 1)} × P95 initial",
            "mesure": f"facteur {nombre(rec['facteur'], 2)} ; santé {c['sante_apres_charge']}",
            "respecte": bool(rec["conforme"] and disponible),
            "marge": "—",
            "marge_num": None,
        },
    ]


# --------------------------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------------------------


def figure_latences(d: dict, chemin: Path) -> None:
    m, o = d["micro_mesures"], d["objectifs"]
    couches = [
        ("inference_service", "Inférence du modèle", o["p95_inference_ms"], "objectif 20 ms"),
        ("chaine_applicative", "Chaîne applicative\n(sans HTTP)", None, None),
        ("api_en_memoire", "API en mémoire\n(TestClient)", o["p95_api_ms"], "objectif 200 ms"),
        ("api_http_local", "API HTTP locale\n(uvicorn)", o["p95_api_ms"], "objectif 200 ms"),
    ]
    fig, ax = plt.subplots(figsize=(LARGEUR, 3.1))
    positions = np.arange(len(couches))[::-1]
    for y, (cle, _etiquette, objectif, texte) in zip(positions, couches, strict=True):
        s = m[cle]
        ax.hlines(y, s["p50_ms"], s["p99_ms"], color=AXE, linewidth=2.2, zorder=2)
        for valeur, couleur in zip(
            (s["p50_ms"], s["p95_ms"], s["p99_ms"]), RAMPE_BLEUE, strict=True
        ):
            ax.scatter(valeur, y, s=62, color=couleur, edgecolor=SURFACE, linewidth=1.6, zorder=4)
        ax.text(
            s["p99_ms"] * 1.35,
            y,
            f"P95 {virgule(s['p95_ms'], 2)} ms",
            va="center",
            fontsize=8.5,
            color=ENCRE,
        )
        if objectif is not None:
            ax.plot([objectif, objectif], [y - 0.26, y + 0.26], color=ENCRE, linewidth=2.2)
            ax.text(
                objectif * 0.92,
                y + 0.34,
                texte,
                ha="right",
                va="bottom",
                fontsize=8,
                color=ENCRE_SECONDAIRE,
            )
    ax.set_xscale("log")
    ax.set_xlim(0.1, 1000)
    ax.set_ylim(-0.7, len(couches) - 0.2)
    ax.set_yticks(positions, [c[1] for c in couches])
    ax.set_xticks([0.1, 1, 10, 100, 1000], ["0,1", "1", "10", "100", "1 000"])
    ax.set_xlabel("Latence d'une requête (ms, échelle logarithmique)")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Latence par couche : P50, P95 et P99 face aux objectifs", pad=10)
    legende = [
        Line2D([], [], marker="o", linestyle="", markersize=7, color=c, markeredgecolor=SURFACE)
        for c in RAMPE_BLEUE
    ]
    ax.legend(
        legende,
        ["P50", "P95", "P99"],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        handletextpad=0.3,
    )
    enregistrer(fig, chemin)


def figure_charge(d: dict, chemin: Path) -> None:
    etapes = d["charge"]["etapes"]
    n = len(etapes)
    x = np.arange(n)
    etiquettes = [str(e["cible_req_s"]) for e in etapes[:-1]] + [
        f"{etapes[-1]['cible_req_s']}\n(retour)"
    ]
    objectif = d["objectifs"]["p95_api_ms"]
    fig, (haut, bas) = plt.subplots(
        2, 1, figsize=(LARGEUR, 5.4), sharex=True, gridspec_kw={"height_ratios": [1.25, 1]}
    )

    def tracer(ax, valeurs, couleur, nom):
        ax.plot(x[:-1], valeurs[:-1], color=couleur, linewidth=2, label=nom, zorder=3)
        ax.scatter(
            x[:-1], valeurs[:-1], s=42, color=couleur, edgecolor=SURFACE, linewidth=1.4, zorder=4
        )
        ax.scatter(
            x[-1], valeurs[-1], s=58, facecolor=SURFACE, edgecolor=couleur, linewidth=1.8, zorder=4
        )

    p50 = [e["p50_ms"] for e in etapes]
    p95 = [e["p95_ms"] for e in etapes]
    tracer(haut, p50, RAMPE_BLEUE[0], "P50")
    tracer(haut, p95, BLEU, "P95")
    haut.axhline(objectif, color=ENCRE, linewidth=1.6, zorder=2)
    haut.text(
        0,
        objectif * 1.12,
        "objectif : P95 ≤ 200 ms",
        fontsize=8.5,
        color=ENCRE_SECONDAIRE,
        va="bottom",
    )
    haut.set_yscale("log")
    haut.set_ylim(1.0, 600)
    haut.set_yticks(
        [1, 2, 5, 10, 20, 50, 100, 200, 500],
        ["1", "2", "5", "10", "20", "50", "100", "200", "500"],
    )
    haut.text(
        n - 1,
        1.12,
        "contrôle après\nsurcharge",
        ha="center",
        va="bottom",
        fontsize=8,
        color=ENCRE_ATTENUEE,
    )
    haut.set_ylabel("Latence (ms, échelle log.)")
    haut.set_title("Charge progressive : latence et CPU selon le débit demandé", pad=10)
    haut.annotate(
        f"P95 = {virgule(p95[-2], 0)} ms\nà {etapes[-2]['cible_req_s']} req/s",
        xy=(n - 2, p95[-2]),
        xytext=(n - 4.6, p95[-2] * 3.1),
        fontsize=8.5,
        color=ENCRE,
        arrowprops={"arrowstyle": "-", "color": ENCRE_ATTENUEE, "linewidth": 0.9},
    )
    haut.legend(loc="upper left", bbox_to_anchor=(0.0, 0.66), ncol=2, handletextpad=0.4)

    cpu_serveur = [e["cpu_serveur_pct"] for e in etapes]
    cpu_generateur = [e["cpu_generateur_pct"] for e in etapes]
    tracer(bas, cpu_serveur, BLEU, "Serveur API (1 cœur)")
    tracer(bas, cpu_generateur, ORANGE, "Générateur de charge (1 cœur)")
    bas.axhline(100, color=ENCRE, linewidth=1.6, zorder=2)
    bas.text(0, 103, "cœur saturé (100 %)", fontsize=8.5, color=ENCRE_SECONDAIRE, va="bottom")
    bas.set_ylim(0, 125)
    bas.set_yticks([0, 25, 50, 75, 100])
    bas.set_ylabel("CPU moyen (% d'un cœur)")
    bas.set_xticks(x, etiquettes)
    bas.set_xlabel("Débit demandé (req/s), paliers successifs de 25 à 30 s")
    bas.legend(loc="upper left", bbox_to_anchor=(0.0, 0.8), ncol=1, handletextpad=0.4)
    fig.align_ylabels()
    enregistrer(fig, chemin)


# --------------------------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------------------------


def section_objectifs(d: dict) -> str:
    o = d["objectifs"]
    h = HYPOTHESES
    debit_pointe = h["agents"] / h["intervalle_s"]
    return f"""## 2. Objectifs de performance et justification

Le prototype est un outil d'aide à la décision utilisé **en interactif** par un agent de crédit :
il saisit les données du demandeur, lit le niveau de risque et poursuit l'entretien. Les objectifs
découlent de cet usage ; ils ne sont pas déduits de ce que le prototype sait faire.

{
        tableau(
            ["Id", "Indicateur", "Objectif", "Justification"],
            [
                [
                    "O1",
                    "Latence d'inférence du modèle, P95",
                    f"≤ {nombre(o['p95_inference_ms'], 0)} ms",
                    "Garde-fou : 10 % du budget de l'API. Détecte le remplacement du modèle par un modèle beaucoup plus lourd.",
                ],
                [
                    "O2",
                    "Temps de réponse de l'API, P95, requêtes valides, charge faible",
                    f"≤ {nombre(o['p95_api_ms'], 0)} ms",
                    "Repères classiques d'ergonomie (Nielsen, 1993) : sous 0,1 s la réponse paraît instantanée, sous 1 s le fil de l'entretien n'est pas rompu. L'API n'est qu'un maillon (réseau, interface) : on lui alloue au plus 20 % de la seconde.",
                ],
                [
                    "O3",
                    "Débit soutenu avec P95 ≤ 200 ms et aucun échec",
                    f"≥ {nombre(o['debit_min_req_s'], 0)} req/s",
                    f"Hypothèse à confirmer avec le métier : {h['agents']} agents, une simulation toutes les {h['intervalle_s']} s en heure de pointe, soit {nombre(debit_pointe, 0)} req/s, avec une marge de ×{nombre(h['marge'], 1)}.",
                ],
                [
                    "O4",
                    "Disponibilité après surcharge",
                    "aucune erreur serveur ; retour au niveau initial",
                    "Une surcharge ne doit pas laisser le service dégradé : après le pic, le P95 revient à au plus 1,5 × sa valeur initiale.",
                ],
            ],
        )
    }

Le P95 est retenu plutôt que la moyenne : il décrit l'expérience de 19 agents sur 20, alors que la
moyenne masque les lenteurs. Les valeurs maximales et le P99 sont rapportés à titre d'information.
"""


def section_configuration(d: dict) -> str:
    c = d["configuration"]
    mat, log, app = c["materiel"], c["logiciel"], c["application"]
    paquets = ", ".join(f"{k} {v}" for k, v in log["paquets"].items() if v)
    lignes = [
        ["Processeur", f"{mat['processeur']} ({entier(mat['frequence_mhz'])} MHz)"],
        [
            "Cœurs",
            f"{mat['coeurs_logiques']} logiques, {mat['coeurs_utilisables']} utilisables ; "
            f"machine virtualisée : {'oui' if mat['virtualise'] else 'non'} ; "
            f"quota CPU : {mat['quota_cpu_cgroup'] or 'aucun'}",
        ],
        ["Mémoire vive", f"{nombre(mat['memoire_vive_go'], 1)} Go"],
        ["Accélérateur", mat["gpu"]],
        ["Système", f"{log['systeme']} (noyau {log['noyau']})"],
        ["Python", f"{log['python']} ({log['implementation']})"],
        [
            "Serveur",
            f"uvicorn, boucle {log['boucle_evenements_uvicorn']}, analyseur HTTP {log['analyseur_http_uvicorn']}, 1 processus",
        ],
        ["Paquets principaux", paquets],
        [
            "Application",
            f"version {app['version_application']}, modèle {app['version_modele']} ({nombre(app['taille_modele_ko'], 1)} Ko), commit {app['commit']}",
        ],
        ["Date des mesures", f"{c['date_utc']} UTC"],
    ]
    return f"""## 3. Configuration matérielle et logicielle

{tableau(["Élément", "Valeur"], lignes)}

Le serveur est épinglé sur le cœur {d["micro_mesures"]["isolement_cpu"]["serveur"]}, le client de mesure (ou Locust) sur le cœur
{d["micro_mesures"]["isolement_cpu"]["client"]} : ils ne se disputent pas le même processeur. Tout se passe sur la boucle locale
(127.0.0.1), sans réseau réel, sans TLS ni proxy.
"""


def section_methode(d: dict) -> str:
    chauffe = d["charge"]["profil"]["chauffe_ignoree_par_palier_s"]
    return f"""## 4. Méthode

- **Latence d'inférence** : appels répétés (3 000 après 200 d'échauffement) sur 300 profils réalistes du
  jeu d'évaluation synthétique ; durée mesurée avec `time.perf_counter_ns`. Deux niveaux : le modèle
  scikit-learn seul et le service applicatif avec ses contrôles (dimensions, finitude, probabilité).
- **Chaîne applicative** : validation, prétraitement, prédiction, interprétation et alertes, sans HTTP.
- **API en mémoire** : `TestClient` (1 000 requêtes) ; **API HTTP locale** : serveur uvicorn réel, un client
  séquentiel avec connexion persistante (1 500 requêtes après 150 d'échauffement).
- **Percentiles** : interpolation linéaire (numpy). Le P95 est la valeur sous laquelle se situent 95 % des durées.
- **Rafales** : N requêtes écrites au même instant sur N connexions ouvertes (client sans surcoût), 15 rafales
  par taille ; pire cas de « tous les agents valident ensemble ».
- **Débit saturé** : 16 clients enchaînant les requêtes sans pause pendant 10 s ; le CPU du serveur est relevé.
- **Charge progressive (Locust)** : {len(d["charge"]["profil"]["etapes"])} paliers de 25 à 30 s ; chaque utilisateur simulé émet en moyenne une requête par
  seconde avec un temps de réflexion exponentiel (arrivées aléatoires). 95 % de requêtes valides, 5 % invalides
  (réponse 422 attendue). Les {nombre(chauffe, 0)} premières secondes de chaque palier sont écartées. Un palier est conforme si
  le P95 des requêtes valides respecte l'objectif et si aucune requête n'échoue. Le CPU du serveur et du générateur est relevé chaque seconde.
- **Piège évité** : avec une cadence rigoureusement constante, Locust synchronise les utilisateurs et crée des
  rafales artificielles (essai préliminaire : 50 utilisateurs, P50 ≈ 54 ms au lieu de ≈ 3 ms). Les arrivées sont donc
  aléatoires, et les rafales réelles sont mesurées à part.
"""


def section_resultats(d: dict) -> str:
    m, c = d["micro_mesures"], d["charge"]
    couches = [
        ("inference_modele_brut", "Modèle seul (`predict_proba`)"),
        ("inference_service", "Service de prédiction (avec contrôles)"),
        ("chaine_applicative", "Chaîne applicative (sans HTTP)"),
        ("api_en_memoire", "API en mémoire (TestClient)"),
        ("api_http_local", "API HTTP locale, requête valide"),
        ("sante_http_local", "API HTTP locale, `/health`"),
    ]
    lat = tableau(
        ["Couche", "n", "P50 (ms)", "P95 (ms)", "P99 (ms)", "Max (ms)", "Débit séquentiel (req/s)"],
        [
            [
                libelle,
                entier(m[cle]["n"]),
                nombre(m[cle]["p50_ms"], 2),
                nombre(m[cle]["p95_ms"], 2),
                nombre(m[cle]["p99_ms"], 2),
                nombre(m[cle]["max_ms"], 2),
                entier(m[cle]["debit_sequentiel_req_s"]),
            ]
            for cle, libelle in couches
        ],
        droite={1, 2, 3, 4, 5, 6},
    )
    rafales = tableau(
        [
            "Requêtes simultanées",
            "P50 (ms)",
            "P95 (ms)",
            "Max (ms)",
            "Durée de la rafale (ms)",
            "Échecs",
        ],
        [
            [
                taille,
                nombre(r["p50_ms"], 0),
                nombre(r["p95_ms"], 0),
                nombre(r["max_ms"], 0),
                nombre(r["duree_rafale_mediane_ms"], 0),
                str(r["echecs"]),
            ]
            for taille, r in m["rafales"].items()
        ],
        droite={0, 1, 2, 3, 4, 5},
    )
    s = m["debit_sature"]
    paliers = tableau(
        [
            "Demandé (req/s)",
            "Observé (req/s)",
            "P50 (ms)",
            "P95 (ms)",
            "P99 (ms)",
            "Max (ms)",
            "Échecs",
            "CPU serveur",
            "CPU générateur",
            "P95 ≤ 200 ms",
        ],
        [
            [
                str(e["cible_req_s"]) + (" (retour)" if i == len(c["etapes"]) - 1 else ""),
                nombre(e["debit_observe_req_s"], 1),
                nombre(e["p50_ms"], 1),
                nombre(e["p95_ms"], 1),
                nombre(e["p99_ms"], 1),
                nombre(e["max_ms"], 1),
                str(e["echecs"]),
                f"{nombre(e['cpu_serveur_pct'], 0)} %",
                f"{nombre(e['cpu_generateur_pct'], 0)} %",
                "oui" if e["conforme_latence"] else "non",
            ]
            for i, e in enumerate(c["etapes"])
        ],
        droite=set(range(10)),
    )
    dem = m["demarrage"]
    memoire = c["memoire_serveur"]
    return f"""## 5. Résultats

### 5.1 Latence par couche

{lat}

![Latence par couche](latences_par_couche.png)

### 5.2 Débit et rafales

Un client unique qui enchaîne les requêtes obtient {entier(m["api_http_local"]["debit_sequentiel_req_s"])} req/s
(c'est l'inverse de la latence : le client attend chaque réponse, ce n'est pas la capacité du serveur).
Avec {s["concurrence"]} clients concurrents sans pause, le serveur
atteint **{entier(s["debit_req_s"])} req/s** avec son cœur à {nombre(s["cpu_serveur_pct"], 0)} % : c'est le plafond d'un processus
uvicorn dans cette configuration (P95 = {nombre(s["p95_ms"], 0)} ms, {s["echecs"]} échec).

Pire cas, N requêtes strictement simultanées (le serveur les traite l'une après l'autre) :

{rafales}

### 5.3 Charge progressive

{paliers}

![Charge progressive](charge_progressive.png)

Sur l'ensemble de l'essai : {entier(c["total_requetes"])} requêtes, {c["total_echecs"]} échecs.
Journal du serveur : {c["erreurs_journal_serveur"]["traceback"]} trace d'erreur, {c["erreurs_journal_serveur"]["statuts_5xx"]} réponse 5xx.
Santé du service après la charge : HTTP {c["sante_apres_charge"]}.

### 5.4 Démarrage et mémoire

Démarrage à froid (lancement du processus jusqu'à la première réponse `/health` positive) :
{nombre(dem["mediane_s"], 1)} s en médiane ({", ".join(nombre(x, 1) for x in dem["durees_s"])} s). Mémoire résidente du
serveur : {nombre(memoire["avant"]["rss_mo"], 0)} Mo avant la charge, {nombre(memoire["apres"]["rss_mo"], 0)} Mo après
({nombre(memoire["apres"]["pic_rss_mo"], 0)} Mo au pic).
"""


def section_interpretation(d: dict) -> str:
    verdicts = evaluer_objectifs(d)
    c, m = d["charge"], d["micro_mesures"]
    essai1 = d.get("charge_essai_precedent", {"total_echecs": 0, "total_requetes": 0})
    lat = c["dernier_palier_latence_conforme"]
    non_conf = c["premier_palier_non_conforme"]
    s = m["debit_sature"]
    tableau_verdicts = tableau(
        ["Id", "Indicateur", "Objectif", "Mesure", "Marge", "Verdict"],
        [
            [
                v["id"],
                v["indicateur"],
                v["objectif"],
                v["mesure"],
                v["marge"],
                "**respecté**" if v["respecte"] else "**non respecté**",
            ]
            for v in verdicts
        ],
    )
    bruit = ""
    if non_conf and non_conf["p95_ms"] <= d["objectifs"]["p95_api_ms"]:
        bruit = (
            f" Le palier à {non_conf['cible_req_s']} req/s est classé non conforme uniquement à cause "
            f"d'échecs isolés (P95 = {nombre(non_conf['p95_ms'], 0)} ms) : des coupures de connexion, "
            "traitées en 6.2."
        )
    objectif_api = d["objectifs"]["p95_api_ms"]
    rafale_max = max(
        (int(t) for t, r in m["rafales"].items() if r["p95_ms"] <= objectif_api), default=0
    )
    rafale_ko = next((t for t, r in m["rafales"].items() if r["p95_ms"] > objectif_api), None)
    p99_depasse = next((e for e in c["etapes"][:-1] if e["p99_ms"] > objectif_api), None)
    marges = [v["marge_num"] for v in verdicts if v["marge_num"]]
    points = []
    if p99_depasse:
        points.append(
            f"- **Premiers signes de saturation** : le P99 dépasse {nombre(objectif_api, 0)} ms dès "
            f"{p99_depasse['cible_req_s']} req/s demandés ({nombre(p99_depasse['p99_ms'], 0)} ms), alors que le P95 "
            f"reste à {nombre(p99_depasse['p95_ms'], 0)} ms ; l'objectif porte sur le P95."
        )
    if rafale_max and rafale_ko is not None:
        r_ok, r_ko = m["rafales"][str(rafale_max)], m["rafales"][rafale_ko]
        points.append(
            f"- **Rafales** : si {rafale_max} agents valident exactement au même instant, le P95 reste à "
            f"{nombre(r_ok['p95_ms'], 0)} ms ; à {rafale_ko} requêtes simultanées il atteint {nombre(r_ko['p95_ms'], 0)} ms. "
            "Le serveur ne rejette rien (aucun échec) : il met les requêtes en file et les traite l'une après l'autre. "
            f"Avec {HYPOTHESES['agents']} agents, ce cas est très improbable ; c'est une limite à connaître."
        )
    points_supplementaires = "\n".join(points)
    return f"""## 6. Interprétation

### 6.1 Les objectifs sont-ils respectés ?

{tableau_verdicts}

- Le **modèle n'est pas le facteur limitant** : l'inférence prend ≈ {nombre(m["inference_service"]["p50_ms"], 2)} ms, alors qu'une requête HTTP complète coûte
  ≈ {nombre(m["api_http_local"]["p50_ms"], 1)} ms. Le temps passe surtout dans la pile HTTP, la validation et la sérialisation. Cette conclusion
  vaut pour une régression logistique ; elle serait à refaire avec un modèle plus lourd.
- Aux débits d'usage prévisibles (≤ 50 req/s) le P95 reste à quelques millisecondes et le serveur utilise moins de
  15 % d'un cœur : la marge est très large.
- Le **P95 respecte l'objectif de 200 ms sur tout le parcours** (jusqu'à {lat["cible_req_s"] if lat else "—"} req/s demandés, P95 = {nombre(lat["p95_ms"], 0) if lat else "—"} ms)
  ; le serveur sature vers {entier(s["debit_req_s"])}–{entier(c["debit_maximal_observe_req_s"])} req/s (cœur à {nombre(c["etapes"][-2]["cpu_serveur_pct"], 0)} % au dernier palier), le générateur n'utilisant que {nombre(c["etapes"][-2]["cpu_generateur_pct"], 0)} % de son cœur : la limite observée est bien celle du serveur.{bruit}
{points_supplementaires}
- **Retour à la normale** : au palier de contrôle ({c["recuperation"]["palier_reference_req_s"]} req/s), le P95 est de
  {nombre(c["recuperation"]["p95_final_ms"], 1)} ms contre {nombre(c["recuperation"]["p95_reference_ms"], 1)} ms avant la montée en charge
  (facteur {nombre(c["recuperation"]["facteur"], 2)}).

### 6.2 Anomalies observées pendant les mesures

1. **Coupures de connexion isolées** : {essai1["total_echecs"]} requêtes sur {entier(essai1["total_requetes"])} (0,005 %) ont échoué lors du premier essai
   complet, contre {c["total_echecs"]} sur {entier(c["total_requetes"])} lors du second. Statut 0 côté client (connexion fermée avant la réponse),
   aucune trace côté serveur. Cause probable, étayée par une expérience dédiée : uvicorn ferme les connexions inactives après 5 s
   (`--timeout-keep-alive`) ; un client qui réutilise la connexion à environ 5,00 s d'inactivité reçoit une
   réinitialisation ou une fermeture (5 essais sur 5 réussis à 4,97 s, 5 sur 5 en échec à 5,03 s, mélange à 5,00 s). Ce lien n'est
   pas prouvé pour les {essai1["total_echecs"]} cas observés. Gravité mineure : à traiter par un délai plus long côté serveur et une relance
   côté client (`POST /predict` est sans effet de bord).
2. **Piège de mesure** : lors d'un essai préliminaire (`essai_preliminaire_cadence_constante.txt`), une cadence strictement
   constante a synchronisé les utilisateurs Locust : avec 50 utilisateurs, le P50 atteignait 54 ms contre ≈ 3 ms avec des
   arrivées aléatoires. Ce n'est pas une anomalie du produit, mais une erreur d'interprétation qui aurait faussé le verdict.

### 6.3 Limites de la mesure

- Machine virtuelle de 2 cœurs partagée entre le serveur et le générateur ; bruit d'ordonnancement non maîtrisé.
- Boucle locale : pas de latence réseau, de TLS, de proxy inverse ni d'authentification.
- Modèle volontairement simple, données synthétiques, profils tirés du jeu d'évaluation.
- Paliers courts (≈ 20 s mesurées) : aux faibles débits l'échantillon est petit (≈ 100 requêtes à 5 req/s), donc le P99 est peu fiable.
  Pas de test d'endurance (fuite mémoire, dérive) ni de test sur plusieurs processus.
- Les objectifs reposent sur des hypothèses d'usage non confirmées par un métier réel.
- Deux exécutions complètes seulement (section 7) : la dispersion près de la saturation n'est pas estimée statistiquement.

### 6.4 Recommandations

1. Conserver O1 à O3 comme garde-fous de non-régression et ajouter une alerte relative (par exemple +50 % du P95 de référence) :
   avec des marges de ×{nombre(min(marges), 0)} à ×{nombre(max(marges), 0)}, une régression sérieuse resterait invisible face aux seuils absolus.
2. En exploitation : `uvicorn[standard]` (uvloop, httptools), plusieurs processus (un par cœur), `--timeout-keep-alive` supérieur
   à l'inactivité des clients, relance côté client.
3. Rejouer cette campagne sur le matériel cible, avec réseau, TLS et authentification, puis réaliser un test d'endurance d'une heure.
4. Confirmer avec le métier le nombre d'agents et la cadence de pointe ; en déduire un nouvel objectif O3 si l'hypothèse change.
"""


def section_reproduction() -> str:
    return """## 8. Reproduire les mesures

```bash
pip install -r requirements-perf.txt
python -m scripts.benchmark_performance            # micro-mesures (≈ 1,5 min)
python -m scripts.benchmark_performance charge     # charge progressive Locust (≈ 5,5 min)
python -m scripts.benchmark_performance rapport    # figures et ce document
```

Les résultats bruts sont dans `reports/performance/` : `performance.json`, `charge_par_palier.csv`,
`charge_par_seconde.csv`, `charge_cpu_par_seconde.csv`, `locust_stats.csv`.
"""


def section_repetabilite(d: dict) -> str:
    essai1 = d.get("charge_essai_precedent")
    if not essai1:
        return ""
    actuel = {e["cible_req_s"]: e for e in d["charge"]["etapes"][:-1]}
    lignes = []
    for ancien in essai1["etapes"][:-1]:
        courant = actuel.get(ancien["cible_req_s"])
        if courant is None:
            continue
        lignes.append(
            [
                str(ancien["cible_req_s"]),
                nombre(ancien["p95_ms"], 1),
                nombre(courant["p95_ms"], 1),
                nombre(ancien["debit_observe_req_s"], 0),
                nombre(courant["debit_observe_req_s"], 0),
            ]
        )
    return f"""## 7. Répétabilité

Deux exécutions complètes de la charge progressive (mêmes paliers, même machine) :

{tableau(["Demandé (req/s)", "P95 essai 1 (ms)", "P95 essai 2 (ms)", "Débit essai 1", "Débit essai 2"], lignes, droite={0, 1, 2, 3, 4})}

Les ordres de grandeur sont stables. Les écarts les plus nets apparaissent près de la saturation, où le temps d'attente
est très sensible au moindre aléa : c'est un argument supplémentaire pour fixer des objectifs avec une large marge.
"""


def produire_rapport(chemin_json: Path) -> None:
    donnees = json.loads(chemin_json.read_text(encoding="utf-8"))
    dossier = chemin_json.parent
    appliquer_style()
    figure_latences(donnees, dossier / "latences_par_couche.png")
    figure_charge(donnees, dossier / "charge_progressive.png")
    donnees["verdicts"] = evaluer_objectifs(donnees)
    chemin_json.write_text(json.dumps(donnees, indent=1, ensure_ascii=False), encoding="utf-8")
    entete = f"""# Rapport de performance : API de prédiction du risque de crédit

Mesures de latence, de débit et de charge progressive du prototype `CreditRisk-Test` (version
{
        donnees["configuration"]["application"]["version_application"]
    }). **Les données sont synthétiques** : les résultats décrivent le comportement
technique du prototype sur cette machine, pas celui d'un système de production.

## 1. Synthèse

{
        tableau(
            ["Id", "Indicateur", "Objectif", "Mesure", "Verdict"],
            [
                [
                    v["id"],
                    v["indicateur"],
                    v["objectif"],
                    v["mesure"],
                    "respecté" if v["respecte"] else "non respecté",
                ]
                for v in donnees["verdicts"]
            ],
        )
    }
"""
    document = "\n".join(
        [
            entete,
            section_objectifs(donnees),
            section_configuration(donnees),
            section_methode(donnees),
            section_resultats(donnees),
            section_interpretation(donnees),
            section_repetabilite(donnees),
            section_reproduction(),
        ]
    )
    (dossier / "rapport_performance.md").write_text(document, encoding="utf-8")
    print("rapport écrit :", dossier / "rapport_performance.md")
