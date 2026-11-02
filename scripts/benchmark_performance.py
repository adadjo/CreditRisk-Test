"""Mesures de performance : latence d'inférence, latence de l'API, débit et charge progressive.

Sous-commandes :

    python -m scripts.benchmark_performance            # micro-mesures : inférence, API, rafales, débit
    python -m scripts.benchmark_performance charge     # charge progressive Locust sur un serveur local
    python -m scripts.benchmark_performance rapport    # synthèse : rapport_performance.md + figures

Les résultats sont fusionnés dans reports/performance/performance.json. Les mesures dépendent de la
machine : la configuration matérielle et logicielle est enregistrée avec chaque résultat.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import metadata, util
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.prediction import ServicePrediction, interpreter_probabilite
from app.preprocessing import construire_caracteristiques
from app.validation import evaluer_alertes, valider_demande
from scripts.profils import charger_profils

DOSSIER = config.RACINE / "reports" / "performance"
SORTIE_JSON = DOSSIER / "performance.json"
TMP = config.RACINE / "reports" / "_tmp"
PORT_MESURE = 8765
PORT_CHARGE = 8766
CHAUFFE_PALIER_S = 7.0  # secondes ignorées au début de chaque palier (montée en charge, connexions)

# Objectifs de performance (justification dans le rapport) : usage interactif d'un agent de crédit.
OBJECTIFS = {
    "p95_inference_ms": 20.0,
    "p95_api_ms": 200.0,
    "debit_min_req_s": 50.0,
    "taux_echec_max": 0.0,
    "recuperation_p95_max_facteur": 1.5,
}

PACKAGES = (
    "fastapi",
    "starlette",
    "uvicorn",
    "numpy",
    "scipy",
    "scikit-learn",
    "joblib",
    "pandas",
    "httpx",
    "locust",
    "pytest",
)


# --------------------------------------------------------------------------------------------
# Configuration matérielle et logicielle
# --------------------------------------------------------------------------------------------


def _lire(chemin: str) -> str:
    try:
        return Path(chemin).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def capturer_configuration() -> dict:
    cpu_modele, frequence, drapeaux = None, None, []
    for ligne in _lire("/proc/cpuinfo").splitlines():
        cle, _, valeur = ligne.partition(":")
        cle, valeur = cle.strip(), valeur.strip()
        if cle == "model name" and cpu_modele is None:
            cpu_modele = valeur
        elif cle == "cpu MHz" and frequence is None:
            frequence = float(valeur)
        elif cle == "flags" and not drapeaux:
            drapeaux = valeur.split()
    memoire_ko = next(
        (
            int(ligne.split()[1])
            for ligne in _lire("/proc/meminfo").splitlines()
            if ligne.startswith("MemTotal")
        ),
        0,
    )
    affinite = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    versions = {}
    for nom in PACKAGES:
        try:
            versions[nom] = metadata.version(nom)
        except metadata.PackageNotFoundError:
            versions[nom] = None
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=config.RACINE,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return {
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "materiel": {
            "processeur": cpu_modele,
            "frequence_mhz": frequence,
            "coeurs_logiques": os.cpu_count(),
            "coeurs_utilisables": len(affinite),
            "memoire_vive_go": round(memoire_ko / 1024 / 1024, 1),
            "virtualise": "hypervisor" in drapeaux,
            "quota_cpu_cgroup": _lire("/sys/fs/cgroup/cpu.max").strip() or None,
            "gpu": "aucun (inférence sur CPU)",
        },
        "logiciel": {
            "systeme": platform.platform(),
            "noyau": platform.release(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "paquets": versions,
            "boucle_evenements_uvicorn": "uvloop" if util.find_spec("uvloop") else "asyncio",
            "analyseur_http_uvicorn": "httptools" if util.find_spec("httptools") else "h11",
        },
        "application": {
            "version_application": config.VERSION_APPLICATION,
            "version_modele": json.loads(config.CHEMIN_METADONNEES.read_text())["version"],
            "taille_modele_ko": round(config.CHEMIN_MODELE.stat().st_size / 1024, 1),
            "commit": commit or None,
            "commande_serveur": (
                "python -m uvicorn app.main:app --host 127.0.0.1 --port <port> "
                "(1 processus, journal d'accès activé)"
            ),
        },
    }


# --------------------------------------------------------------------------------------------
# Outils de mesure
# --------------------------------------------------------------------------------------------


def statistiques(durees_ms, avec_debit: bool = True) -> dict:
    """Résumé d'un échantillon de durées (ms) ; percentiles par interpolation linéaire (numpy)."""
    a = np.asarray(durees_ms, dtype=float)
    p50, p95, p99 = np.percentile(a, [50, 95, 99])
    resultat = {
        "n": int(a.size),
        "moyenne_ms": round(float(a.mean()), 4),
        "ecart_type_ms": round(float(a.std(ddof=1)), 4) if a.size > 1 else 0.0,
        "min_ms": round(float(a.min()), 4),
        "p50_ms": round(float(p50), 4),
        "p95_ms": round(float(p95), 4),
        "p99_ms": round(float(p99), 4),
        "max_ms": round(float(a.max()), 4),
    }
    if avec_debit:  # requêtes enchaînées par un client unique : 1 / durée moyenne
        resultat["debit_sequentiel_req_s"] = round(float(a.size / (a.sum() / 1000)), 1)
    return resultat


def chronometrer(action, repetitions: int, echauffement: int) -> np.ndarray:
    """Durée (ms) de `repetitions` appels successifs, après un échauffement non mesuré."""
    for _ in range(echauffement):
        action()
    durees = np.empty(repetitions)
    for i in range(repetitions):
        debut = time.perf_counter_ns()
        action()
        durees[i] = (time.perf_counter_ns() - debut) / 1_000_000
    return durees


def lire_memoire(pid: int) -> dict:
    """Mémoire résidente (Mo) d'un processus : valeur courante et pic."""
    valeurs = {}
    for ligne in _lire(f"/proc/{pid}/status").splitlines():
        if ligne.startswith(("VmRSS", "VmHWM")):
            valeurs[ligne.split(":")[0]] = round(int(ligne.split()[1]) / 1024, 1)
    return {"rss_mo": valeurs.get("VmRSS"), "pic_rss_mo": valeurs.get("VmHWM")}


def _epingleur(coeur: int | None):
    def appliquer() -> None:
        if coeur is not None and hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, {coeur})

    return appliquer


def choisir_coeurs() -> tuple[int | None, int | None]:
    """Un cœur pour le serveur, un autre pour le client de mesure (si la machine en a deux)."""
    if not hasattr(os, "sched_getaffinity"):
        return None, None
    coeurs = sorted(os.sched_getaffinity(0))
    return (coeurs[0], coeurs[1]) if len(coeurs) >= 2 else (None, None)


def attendre_sante(url: str, processus: subprocess.Popen, delai_s: float = 60.0) -> None:
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        if processus.poll() is not None:
            raise RuntimeError("le serveur s'est arrêté avant d'être prêt")
        try:
            if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise TimeoutError("le serveur n'est pas devenu disponible à temps")


@contextmanager
def serveur_local(port: int, coeur: int | None = None):
    """Lance uvicorn (1 processus) et renvoie (processus, url, durée de démarrage en s)."""
    TMP.mkdir(parents=True, exist_ok=True)
    journal = (TMP / f"uvicorn_{port}.log").open("wb")
    debut = time.perf_counter()
    processus = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=config.RACINE,
        stdout=journal,
        stderr=subprocess.STDOUT,
        preexec_fn=_epingleur(coeur),
    )
    url = f"http://127.0.0.1:{port}"
    try:
        attendre_sante(url, processus)
        yield processus, url, time.perf_counter() - debut
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.wait()
        journal.close()


def verifier_profils(profils: list[dict]) -> None:
    """Les profils de mesure doivent tous être valides : on mesure le chemin nominal."""
    for profil in profils:
        valider_demande(profil)


def enregistrer(section: str, contenu: dict, configuration: dict | None = None) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    donnees = json.loads(SORTIE_JSON.read_text(encoding="utf-8")) if SORTIE_JSON.exists() else {}
    donnees[section] = contenu
    donnees["objectifs"] = OBJECTIFS
    if configuration is not None:
        donnees["configuration"] = configuration
    SORTIE_JSON.write_text(json.dumps(donnees, indent=1, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Micro-mesures
# --------------------------------------------------------------------------------------------


def lire_cpu_s(pid: int) -> float | None:
    """Temps CPU cumulé (utilisateur + système) d'un processus, en secondes."""
    try:
        champs = _lire(f"/proc/{pid}/stat").rsplit(")", 1)[1].split()
        return (int(champs[11]) + int(champs[12])) / os.sysconf("SC_CLK_TCK")
    except (IndexError, ValueError, OSError):
        return None


def _requete_http(charge: dict) -> bytes:
    corps = json.dumps(charge).encode()
    en_tete = (
        "POST /predict HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(corps)}\r\n\r\n"
    )
    return en_tete.encode() + corps


async def _lire_reponse(lecteur: asyncio.StreamReader) -> int:
    """Lit une réponse HTTP/1.1 complète et renvoie son statut."""
    en_tetes = await lecteur.readuntil(b"\r\n\r\n")
    statut = int(en_tetes.split(b" ", 2)[1])
    for ligne in en_tetes.split(b"\r\n"):
        if ligne.lower().startswith(b"content-length:"):
            await lecteur.readexactly(int(ligne.split(b":")[1]))
    return statut


async def mesurer_rafales(
    port: int, profils: list[dict], tailles=(10, 25, 50, 100, 200), repetitions: int = 15
) -> dict:
    """Pire cas : N agents qui valident exactement au même instant (arrivées synchronisées).

    Le client écrit directement sur N connexions déjà ouvertes (aucun surcoût de bibliothèque
    HTTP) : la latence mesurée est celle du serveur, y compris l'attente dans sa file.
    """
    cycle = itertools.cycle(profils)
    resultats = {}
    for taille in tailles:
        connexions = [await asyncio.open_connection("127.0.0.1", port) for _ in range(taille)]
        sante = b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        for _, ecrivain in connexions:  # une requête par connexion : le serveur les initialise
            ecrivain.write(sante)
        await asyncio.gather(*(_lire_reponse(lecteur) for lecteur, _ in connexions))
        durees: list[float] = []
        totaux: list[float] = []
        echecs = 0
        for essai in range(repetitions + 2):
            requetes = [_requete_http(next(cycle)) for _ in range(taille)]
            debut = time.perf_counter()
            for (_, ecrivain), requete in zip(connexions, requetes, strict=True):
                ecrivain.write(requete)

            async def attendre(lecteur: asyncio.StreamReader, origine: float = debut):
                statut = await _lire_reponse(lecteur)
                return (time.perf_counter() - origine) * 1000, statut

            lot = await asyncio.gather(*(attendre(lecteur) for lecteur, _ in connexions))
            if essai >= 2:  # les deux premières rafales servent d'échauffement
                durees += [duree for duree, _ in lot]
                totaux.append(max(duree for duree, _ in lot))
                echecs += sum(statut != 200 for _, statut in lot)
            await asyncio.sleep(0.4)
        for _, ecrivain in connexions:
            ecrivain.close()
        mediane_ms = float(np.median(totaux))
        resultats[str(taille)] = {
            **statistiques(durees, avec_debit=False),
            "rafales": repetitions,
            "echecs": echecs,
            "duree_rafale_mediane_ms": round(mediane_ms, 1),
            "debit_pendant_rafale_req_s": round(taille / (mediane_ms / 1000)),
        }
    return resultats


async def mesurer_debit_sature(
    url: str,
    profils: list[dict],
    pid_serveur: int,
    concurrence: int = 16,
    duree_s: float = 10.0,
    chauffe_s: float = 2.0,
) -> dict:
    """Boucle fermée : `concurrence` clients qui enchaînent les requêtes sans pause (saturation)."""
    cycle = itertools.cycle(profils)
    durees: list[float] = []
    echecs = 0
    debut_mesure = time.perf_counter() + chauffe_s
    arret = debut_mesure + duree_s

    async def travailleur(client: httpx.AsyncClient) -> None:
        nonlocal echecs
        while (debut := time.perf_counter()) < arret:
            reponse = await client.post("/predict", json=next(cycle))
            if debut >= debut_mesure:
                durees.append((time.perf_counter() - debut) * 1000)
                echecs += reponse.status_code != 200

    async def sonde_cpu() -> float | None:
        await asyncio.sleep(chauffe_s)
        t0, c0 = time.perf_counter(), lire_cpu_s(pid_serveur)
        await asyncio.sleep(duree_s)
        t1, c1 = time.perf_counter(), lire_cpu_s(pid_serveur)
        return None if c0 is None or c1 is None else 100 * (c1 - c0) / (t1 - t0)

    limites = httpx.Limits(max_connections=concurrence, max_keepalive_connections=concurrence)
    async with httpx.AsyncClient(base_url=url, timeout=30.0, limits=limites) as client:
        *_, cpu_serveur = await asyncio.gather(
            *(travailleur(client) for _ in range(concurrence)), sonde_cpu()
        )
    return {
        "concurrence": concurrence,
        "duree_mesure_s": duree_s,
        "debit_req_s": round(len(durees) / duree_s, 1),
        "echecs": echecs,
        "cpu_serveur_pct": None if cpu_serveur is None else round(cpu_serveur, 1),
        **{
            cle: valeur
            for cle, valeur in statistiques(durees, avec_debit=False).items()
            if cle in ("n", "p50_ms", "p95_ms", "p99_ms", "max_ms")
        },
    }


def mesurer(repetitions: int = 3000) -> dict:
    profils = charger_profils(300)
    verifier_profils(profils)
    service = ServicePrediction()
    service.charger()
    matrices = [construire_caracteristiques(valider_demande(p)) for p in profils]
    modele_brut = joblib.load(config.CHEMIN_MODELE)
    resultats: dict = {}

    cycle_x = itertools.cycle(matrices)
    resultats["inference_modele_brut"] = statistiques(
        chronometrer(lambda: modele_brut.predict_proba(next(cycle_x)), repetitions, 200)
    )
    cycle_x = itertools.cycle(matrices)
    resultats["inference_service"] = statistiques(
        chronometrer(lambda: service.predire(next(cycle_x)), repetitions, 200)
    )

    cycle_p = itertools.cycle(profils)

    def traiter_une_demande() -> None:
        demande = valider_demande(next(cycle_p))
        probabilite = service.predire(construire_caracteristiques(demande))
        interpreter_probabilite(probabilite)
        evaluer_alertes(demande, service.domaine_entrainement)

    resultats["chaine_applicative"] = statistiques(
        chronometrer(traiter_une_demande, repetitions, 200)
    )

    lot = np.vstack(list(itertools.islice(itertools.cycle(matrices), 1000)))
    durees_lot = chronometrer(lambda: modele_brut.predict_proba(lot), 100, 10)
    mediane_lot = float(np.median(durees_lot))
    resultats["modele_lot_1000"] = {
        "taille_lot": 1000,
        "duree_mediane_ms": round(mediane_lot, 3),
        "predictions_par_s": round(1000 / (mediane_lot / 1000)),
    }

    client = TestClient(create_app(service))
    cycle_p = itertools.cycle(profils)

    def appeler_en_memoire() -> None:
        reponse = client.post("/predict", json=next(cycle_p))
        if reponse.status_code != 200:
            raise RuntimeError(f"statut inattendu {reponse.status_code}")

    resultats["api_en_memoire"] = statistiques(chronometrer(appeler_en_memoire, 1000, 100))

    coeur_serveur, coeur_client = choisir_coeurs()
    affinite_initiale = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else None
    demarrages = []
    with serveur_local(PORT_MESURE, coeur_serveur) as (processus, url, duree_demarrage):
        demarrages.append(duree_demarrage)
        memoire_demarrage = lire_memoire(processus.pid)
        if coeur_client is not None:
            os.sched_setaffinity(0, {coeur_client})
        with httpx.Client(base_url=url, timeout=10.0) as http:
            cycle_p = itertools.cycle(profils)

            def appeler_http() -> None:
                reponse = http.post("/predict", json=next(cycle_p))
                if reponse.status_code != 200:
                    raise RuntimeError(f"statut inattendu {reponse.status_code}")

            resultats["api_http_local"] = statistiques(chronometrer(appeler_http, 1500, 150))
            resultats["sante_http_local"] = statistiques(
                chronometrer(lambda: http.get("/health"), 500, 50)
            )
        resultats["rafales"] = asyncio.run(mesurer_rafales(PORT_MESURE, profils))
        resultats["debit_sature"] = asyncio.run(mesurer_debit_sature(url, profils, processus.pid))
        memoire_apres = lire_memoire(processus.pid)
        if affinite_initiale is not None:
            os.sched_setaffinity(0, affinite_initiale)
    for _ in range(2):
        with serveur_local(PORT_MESURE, coeur_serveur) as (_, _, duree_demarrage):
            demarrages.append(duree_demarrage)

    resultats["demarrage"] = {
        "durees_s": [round(d, 2) for d in demarrages],
        "mediane_s": round(float(np.median(demarrages)), 2),
        "definition": "lancement du processus uvicorn jusqu'à la première réponse 200 de /health",
    }
    resultats["memoire_serveur"] = {
        "apres_demarrage": memoire_demarrage,
        "apres_les_mesures": memoire_apres,
    }
    resultats["isolement_cpu"] = {"serveur": coeur_serveur, "client": coeur_client}
    return resultats


# --------------------------------------------------------------------------------------------
# Charge progressive (Locust)
# --------------------------------------------------------------------------------------------


def _moyenne_cpu(echantillons: list[dict], cle: str, debut: float, fin: float) -> float | None:
    valeurs = [e[cle] for e in echantillons if debut <= e["t_epoch"] < fin]
    return round(float(np.mean(valeurs)), 1) if valeurs else None


def analyser_journal(
    journal: Path,
    profil: dict,
    objectifs: dict = OBJECTIFS,
    echantillons_cpu: list[dict] | None = None,
) -> dict:
    """Statistiques exactes par palier à partir du journal de toutes les requêtes.

    Un palier est conforme si le P95 des requêtes valides respecte l'objectif et si aucune requête
    n'a échoué (erreur, time-out ou statut inattendu). Le débit observé est informatif : avec des
    arrivées aléatoires et des utilisateurs qui attendent leur réponse, il est légèrement inférieur
    au débit demandé même sans saturation.
    """
    df = pd.read_csv(journal)
    cpu = echantillons_cpu or []
    origine = profil.get("debut_epoch", 0.0)
    etapes = []
    debut = 0.0
    for indice, (cible, duree) in enumerate(profil["etapes"]):
        fin = debut + duree
        fenetre = df[(df.t_s >= debut + CHAUFFE_PALIER_S) & (df.t_s < fin)]
        valides = fenetre[fenetre.nom == "/predict [valide]"].duree_ms
        invalides = fenetre[fenetre.nom == "/predict [invalide]"].duree_ms
        duree_mesure = duree - CHAUFFE_PALIER_S
        echecs = int((fenetre.succes == 0).sum())
        p50, p95, p99 = (
            (float(x) for x in np.percentile(valides, [50, 95, 99]))
            if len(valides)
            else (None,) * 3
        )
        latence_ok = bool(p95 is not None and p95 <= objectifs["p95_api_ms"])
        conforme = latence_ok and echecs == 0
        etapes.append(
            {
                "palier": indice + 1,
                "cible_req_s": cible,
                "duree_palier_s": duree,
                "duree_mesuree_s": duree_mesure,
                "n_requetes": int(len(fenetre)),
                "n_valides": int(len(valides)),
                "debit_observe_req_s": round(len(fenetre) / duree_mesure, 1),
                "p50_ms": None if p50 is None else round(p50, 2),
                "p95_ms": None if p95 is None else round(p95, 2),
                "p99_ms": None if p99 is None else round(p99, 2),
                "max_ms": round(float(valides.max()), 2) if len(valides) else None,
                "p95_invalides_ms": (
                    round(float(np.percentile(invalides, 95)), 2) if len(invalides) else None
                ),
                "echecs": echecs,
                "taux_echec": round(echecs / len(fenetre), 5) if len(fenetre) else None,
                "cpu_serveur_pct": _moyenne_cpu(
                    cpu, "serveur_pct", origine + debut + CHAUFFE_PALIER_S, origine + fin
                ),
                "cpu_generateur_pct": _moyenne_cpu(
                    cpu, "generateur_pct", origine + debut + CHAUFFE_PALIER_S, origine + fin
                ),
                "conforme_latence": latence_ok,
                "conforme_objectif": conforme,
            }
        )
        debut = fin

    montee, final = etapes[:-1], etapes[-1]
    dernier_conforme, limite = None, None
    for etape in montee:
        if etape["conforme_objectif"]:
            dernier_conforme = etape
        else:
            limite = etape
            break
    dernier_latence = None
    for etape in montee:
        if not etape["conforme_latence"]:
            break
        dernier_latence = etape
    reference = next((e for e in montee if e["cible_req_s"] == final["cible_req_s"]), montee[0])
    seconde = df.assign(seconde=df.t_s.astype(int))
    par_seconde = []
    for s, groupe in seconde.groupby("seconde"):
        valides = groupe[groupe.nom == "/predict [valide]"].duree_ms
        par_seconde.append(
            {
                "t_s": int(s),
                "requetes": int(len(groupe)),
                "echecs": int((groupe.succes == 0).sum()),
                "p95_ms": round(float(np.percentile(valides, 95)), 2) if len(valides) else None,
            }
        )
    facteur = (
        round(final["p95_ms"] / reference["p95_ms"], 2)
        if reference["p95_ms"] and final["p95_ms"]
        else None
    )
    return {
        "etapes": etapes,
        "dernier_palier_conforme": None
        if dernier_conforme is None
        else {
            "cible_req_s": dernier_conforme["cible_req_s"],
            "debit_observe_req_s": dernier_conforme["debit_observe_req_s"],
            "p95_ms": dernier_conforme["p95_ms"],
        },
        "dernier_palier_latence_conforme": None
        if dernier_latence is None
        else {
            "cible_req_s": dernier_latence["cible_req_s"],
            "debit_observe_req_s": dernier_latence["debit_observe_req_s"],
            "p95_ms": dernier_latence["p95_ms"],
        },
        "premier_palier_non_conforme": None
        if limite is None
        else {
            "cible_req_s": limite["cible_req_s"],
            "debit_observe_req_s": limite["debit_observe_req_s"],
            "p95_ms": limite["p95_ms"],
            "echecs": limite["echecs"],
        },
        "debit_maximal_observe_req_s": max(e["debit_observe_req_s"] for e in montee),
        "recuperation": {
            "palier_reference_req_s": reference["cible_req_s"],
            "p95_reference_ms": reference["p95_ms"],
            "p95_final_ms": final["p95_ms"],
            "facteur": facteur,
            "echecs_palier_final": final["echecs"],
            "conforme": bool(
                facteur is not None
                and facteur <= objectifs["recuperation_p95_max_facteur"]
                and final["echecs"] == 0
            ),
        },
        "par_seconde": par_seconde,
        "total_requetes": int(len(df)),
        "total_echecs": int((df.succes == 0).sum()),
    }


def executer_charge() -> dict:
    TMP.mkdir(parents=True, exist_ok=True)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    journal = TMP / "locust_journal.csv"
    journal_stdout = TMP / "locust_sortie.txt"
    profils = charger_profils(300)
    verifier_profils(profils)
    coeur_serveur, coeur_generateur = choisir_coeurs()
    echantillons: list[dict] = []
    with serveur_local(PORT_CHARGE, coeur_serveur) as (processus, url, demarrage):
        for profil in profils:  # contrôle préalable : tous les profils doivent être acceptés
            if httpx.post(f"{url}/predict", json=profil, timeout=10).status_code != 200:
                raise RuntimeError("un profil de mesure est refusé par l'API")
        memoire_avant = lire_memoire(processus.pid)
        commande = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            "scripts/locustfile.py",
            "--headless",
            "--host",
            url,
            "--csv",
            str(TMP / "locust"),
            "--only-summary",
        ]
        debut = time.perf_counter()
        with journal_stdout.open("wb") as sortie:
            generateur = subprocess.Popen(
                commande,
                cwd=config.RACINE,
                env={**os.environ, "LOCUST_JOURNAL": str(journal)},
                stdout=sortie,
                stderr=subprocess.STDOUT,
                preexec_fn=_epingleur(coeur_generateur),
            )
            try:
                precedent = (time.time(), lire_cpu_s(processus.pid), lire_cpu_s(generateur.pid))
                while generateur.poll() is None and time.perf_counter() - debut < 900:
                    time.sleep(1.0)
                    t, cpu_serveur, cpu_generateur = (
                        time.time(),
                        lire_cpu_s(processus.pid),
                        lire_cpu_s(generateur.pid),
                    )
                    if None not in (cpu_serveur, cpu_generateur, precedent[1], precedent[2]):
                        dt = t - precedent[0]
                        echantillons.append(
                            {
                                "t_epoch": t,
                                "serveur_pct": 100 * (cpu_serveur - precedent[1]) / dt,
                                "generateur_pct": 100 * (cpu_generateur - precedent[2]) / dt,
                            }
                        )
                    precedent = (t, cpu_serveur, cpu_generateur)
            finally:
                if generateur.poll() is None:
                    generateur.terminate()
                code_retour = generateur.wait()
        duree_reelle = time.perf_counter() - debut
        memoire_apres = lire_memoire(processus.pid)
        sante_apres = httpx.get(f"{url}/health", timeout=5).status_code
    profil = json.loads(journal.with_suffix(".profil.json").read_text(encoding="utf-8"))
    analyse = analyser_journal(journal, profil, echantillons_cpu=echantillons)
    sortie = journal_stdout.read_text(encoding="utf-8", errors="replace")
    journal_serveur = (TMP / f"uvicorn_{PORT_CHARGE}.log").read_text(
        encoding="utf-8", errors="replace"
    )
    stats_locust = TMP / "locust_stats.csv"
    if stats_locust.exists():
        shutil.copyfile(stats_locust, DOSSIER / "locust_stats.csv")
    pd.DataFrame(analyse["etapes"]).to_csv(DOSSIER / "charge_par_palier.csv", index=False)
    pd.DataFrame(analyse["par_seconde"]).to_csv(DOSSIER / "charge_par_seconde.csv", index=False)
    pd.DataFrame(echantillons).assign(
        t_s=lambda d: (d.t_epoch - profil["debut_epoch"]).round(1)
    ).drop(columns="t_epoch").round(1).to_csv(DOSSIER / "charge_cpu_par_seconde.csv", index=False)
    return {
        "profil": {
            "etapes": profil["etapes"],
            "debit_par_utilisateur_req_s": profil["debit_par_utilisateur"],
            "arrivees": "aléatoires (temps de réflexion exponentiel, moyenne 1 s par utilisateur)",
            "part_requetes_invalides": profil["part_requetes_invalides"],
            "chauffe_ignoree_par_palier_s": CHAUFFE_PALIER_S,
            "generateur": "Locust FastHttpUser, 1 processus",
        },
        "isolement_cpu": {"serveur": coeur_serveur, "generateur": coeur_generateur},
        "duree_reelle_s": round(duree_reelle, 1),
        "code_retour_locust": code_retour,
        "avertissement_cpu_generateur": "CPU usage above 90%" in sortie,
        "demarrage_serveur_s": round(demarrage, 2),
        "memoire_serveur": {"avant": memoire_avant, "apres": memoire_apres},
        "sante_apres_charge": sante_apres,
        "erreurs_journal_serveur": {
            "traceback": journal_serveur.count("Traceback"),
            "statuts_5xx": sum(f'" {code} ' in journal_serveur for code in (500, 502, 503, 504)),
        },
        **analyse,
    }


# --------------------------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------------------------


def afficher_micro_mesures(resultats: dict) -> None:
    for nom, valeur in resultats.items():
        if isinstance(valeur, dict) and "p95_ms" in valeur and "debit_sequentiel_req_s" in valeur:
            print(
                f"{nom:24s} n={valeur['n']:5d}  P50={valeur['p50_ms']:8.3f}  "
                f"P95={valeur['p95_ms']:8.3f}  P99={valeur['p99_ms']:8.3f} ms  "
                f"{valeur['debit_sequentiel_req_s']:8.1f} req/s (séquentiel)"
            )
    for taille, r in resultats["rafales"].items():
        print(
            f"rafale de {taille:>3s} requêtes simultanées : P50={r['p50_ms']:7.1f}  "
            f"P95={r['p95_ms']:7.1f}  max={r['max_ms']:7.1f} ms  "
            f"durée totale médiane={r['duree_rafale_mediane_ms']:7.1f} ms  échecs={r['echecs']}"
        )
    print("débit saturé :", json.dumps(resultats["debit_sature"], ensure_ascii=False))
    print(json.dumps({k: resultats[k] for k in ("modele_lot_1000", "demarrage")}, indent=1))


def afficher_charge(donnees: dict) -> None:
    for e in donnees["etapes"]:
        print(
            f"cible {e['cible_req_s']:4d} req/s -> {e['debit_observe_req_s']:7.1f} req/s  "
            f"P50={e['p50_ms']}  P95={e['p95_ms']}  P99={e['p99_ms']} ms  échecs={e['echecs']}  "
            f"CPU serveur={e['cpu_serveur_pct']} %  CPU générateur={e['cpu_generateur_pct']} %  "
            f"conforme={e['conforme_objectif']}"
        )
    print("dernier palier conforme :", donnees["dernier_palier_conforme"])
    print("premier palier non conforme :", donnees["premier_palier_non_conforme"])
    print("récupération :", donnees["recuperation"])


def main(argv: list[str] | None = None) -> None:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument(
        "commande", nargs="?", default="mesurer", choices=["mesurer", "charge", "rapport"]
    )
    arguments = analyseur.parse_args(argv)
    if arguments.commande == "mesurer":
        resultats = mesurer()
        enregistrer("micro_mesures", resultats, capturer_configuration())
        afficher_micro_mesures(resultats)
    elif arguments.commande == "charge":
        enregistrer("charge", executer_charge())
        afficher_charge(json.loads(SORTIE_JSON.read_text(encoding="utf-8"))["charge"])
    else:
        from scripts.rapport_performance import produire_rapport

        produire_rapport(SORTIE_JSON)


if __name__ == "__main__":
    main()
