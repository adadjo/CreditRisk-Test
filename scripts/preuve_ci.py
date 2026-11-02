"""Preuve locale de la chaîne d'intégration continue (réplique de .github/workflows/tests.yml).

Rejoue, dans l'ordre et avec les mêmes commandes que le workflow :
  1. ruff check . ;
  2. ruff format --check . ;
  3. pytest avec couverture (seuil 90 %), rapports XML, HTML, JUnit et JSON ;
puis démontre que la chaîne bloque :
  4. un test volontairement défaillant (DEMO_ECHEC=1), avec la commande complète du workflow ;
  5. des défauts injectés un par un dans une copie temporaire du code.
Le résultat est écrit dans reports/preuve_ci_locale.md.

Ce script n'utilise que la bibliothèque standard : il peut piloter un autre interpréteur
(par exemple celui d'un environnement virtuel vierge) avec l'option --python.

Usage : python -m scripts.preuve_ci [--venv-vierge | --python chemin/vers/python] [--sans-mutations]

--venv-vierge crée un environnement virtuel neuf, y installe requirements.txt puis l'utilise :
c'est ce que fait un runner GitHub Actions avant ses premières commandes.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "reports" / "preuve_ci_locale.md"
TMP = RACINE / "reports" / "_tmp"

MUTATIONS = [
    {
        "id": "M1",
        "description": "Seuil de risque élevé : `p < 0,60` devient `p <= 0,60` (défaut observé en v0.1)",
        "fichier": "app/prediction.py",
        "ancien": "    if probabilite < config.SEUIL_RISQUE_ELEVE:",
        "nouveau": "    if probabilite <= config.SEUIL_RISQUE_ELEVE:",
    },
    {
        "id": "M2",
        "description": "Borne minimale d'un champ exclue : `minimum <= valeur` devient `minimum < valeur`",
        "fichier": "app/validation.py",
        "ancien": "    if not limite.minimum <= valeur <= limite.maximum:",
        "nouveau": "    if not limite.minimum < valeur <= limite.maximum:",
    },
    {
        "id": "M3",
        "description": "Garde de plage supprimée : une probabilité hors de [0, 1] n'est plus refusée",
        "fichier": "app/prediction.py",
        "ancien": "        if not math.isfinite(probabilite) or not 0.0 <= probabilite <= 1.0:",
        "nouveau": "        if not math.isfinite(probabilite):",
    },
    {
        "id": "M4",
        "description": "Contrôle d'intégrité SHA-256 du modèle désactivé",
        "fichier": "app/prediction.py",
        "ancien": '                if calculer_empreinte(self.chemin_modele) != metadonnees["empreinte_sha256"]:',
        "nouveau": "                if False:",
    },
    {
        "id": "M5",
        "description": "Les booléens sont acceptés comme des nombres (`true` -> 1)",
        "fichier": "app/validation.py",
        "ancien": "    if isinstance(valeur, bool) or not isinstance(valeur, int | float):",
        "nouveau": "    if not isinstance(valeur, int | float):",
    },
    {
        "id": "M6",
        "description": "Contrôle des valeurs non finies (infini issu de `1e999`) supprimé",
        "fichier": "app/validation.py",
        "ancien": "    if isinstance(valeur, float) and not math.isfinite(valeur):",
        "nouveau": "    if False:",
    },
    {
        "id": "M7",
        "description": "Cohérence âge / ancienneté : `>` devient `>=` (un cas limite valide est refusé)",
        "fichier": "app/validation.py",
        "ancien": '        if valeurs["anciennete_activite"] > plafond:',
        "nouveau": '        if valeurs["anciennete_activite"] >= plafond:',
    },
    {
        "id": "M8",
        "description": "Taux d'effort mal calculé : `montant / durée` devient `montant * durée`",
        "fichier": "app/preprocessing.py",
        "ancien": "            taux_effort = (montant / duree) / revenu",
        "nouveau": "            taux_effort = (montant * duree) / revenu",
    },
    {
        "id": "M9",
        "description": "Colonnes `log_revenu` et `log_montant` permutées (décalage entraînement / service)",
        "fichier": "app/preprocessing.py",
        "ancien": "[age, np.log(revenu), np.log(montant), duree, anciennete, taux_effort]",
        "nouveau": "[age, np.log(montant), np.log(revenu), duree, anciennete, taux_effort]",
    },
    {
        "id": "M10",
        "description": "L'en-tête `Retry-After` n'est plus envoyé avec le 503",
        "fichier": "app/main.py",
        "ancien": '503, "modele_indisponible", MESSAGE_MODELE, id_requete, entetes={"Retry-After": "30"}',
        "nouveau": '503, "modele_indisponible", MESSAGE_MODELE, id_requete, entetes=None',
    },
    {
        "id": "M11",
        "description": "Contrôle du Content-Type supprimé (plus de 415)",
        "fichier": "app/main.py",
        "ancien": '        if type_contenu != "application/json":',
        "nouveau": "        if False:",
    },
    {
        "id": "M12",
        "description": "Taille maximale du corps de requête portée de 10 000 octets à 10 Mo",
        "fichier": "app/config.py",
        "ancien": "TAILLE_MAX_CORPS = 10_000",
        "nouveau": "TAILLE_MAX_CORPS = 10_000_000",
    },
    {
        "id": "M13",
        "description": "L'identifiant de requête n'est plus renvoyé dans l'en-tête `X-Request-ID`",
        "fichier": "app/main.py",
        "ancien": '        reponse.headers["X-Request-ID"] = id_requete',
        "nouveau": "        pass",
    },
    {
        "id": "M14",
        "description": "Seuil de risque modéré modifié : 0,30 devient 0,35",
        "fichier": "app/config.py",
        "ancien": "SEUIL_RISQUE_MODERE = 0.30",
        "nouveau": "SEUIL_RISQUE_MODERE = 0.35",
    },
    {
        "id": "M15",
        "description": "Contrôle de conformité du modèle chargé : nombre de variables ignoré",
        "fichier": "app/prediction.py",
        "ancien": '                    and getattr(modele, "n_features_in_", None) == len(VARIABLES_MODELE)',
        "nouveau": "                    and True",
    },
]


def commande_pytest(dossier_rapports: str) -> list[str]:
    """Arguments de pytest identiques à ceux du workflow (seuls les chemins de sortie varient)."""
    return [
        "-m",
        "pytest",
        "--cov=app",
        "--cov=ml",
        "--cov-report=term-missing",
        f"--cov-report=xml:{dossier_rapports}/coverage.xml",
        f"--cov-report=html:{dossier_rapports}/htmlcov",
        "--cov-fail-under=90",
        f"--junitxml={dossier_rapports}/junit.xml",
        f"--resultats-json={dossier_rapports}/resultats_tests.json",
    ]


def executer(python: str, arguments: list[str], cwd: Path, env_extra: dict | None = None) -> dict:
    env = {**os.environ, **(env_extra or {})}
    if not env_extra or "DEMO_ECHEC" not in env_extra:
        env.pop("DEMO_ECHEC", None)  # l'étape nominale ne doit jamais activer l'échec volontaire
    debut = time.perf_counter()
    resultat = subprocess.run(
        [python, *arguments], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    sortie = (resultat.stdout + resultat.stderr).strip()
    return {
        "code": resultat.returncode,
        "duree_s": round(time.perf_counter() - debut, 1),
        "sortie": sortie,
    }


def resume_pytest(sortie: str) -> dict:
    """Extrait de la sortie de pytest la ligne de bilan, la couverture et les tests en échec."""
    bilan = re.findall(
        r"(\d+ (?:failed|passed|skipped|errors?|deselected|xfailed|xpassed|warnings?)"
        r"(?:, \d+ [a-z]+)* in [\d.]+s(?: \(\d+:\d{2}:\d{2}\))?)",
        sortie,
    )
    couverture = re.findall(r"Total coverage: (\d+(?:\.\d+)?)%", sortie) or re.findall(
        r"^TOTAL\s+.*?(\d+(?:\.\d+)?)%", sortie, flags=re.M
    )
    seuil = re.findall(r"(Required test coverage of \d+% (?:reached|not reached)[^\n]*)", sortie)
    echecs = re.findall(r"^FAILED (\S+)", sortie, flags=re.M)
    return {
        "bilan": bilan[-1] if bilan else None,
        "couverture": couverture[-1] if couverture else None,
        "seuil": seuil[-1] if seuil else None,
        "echecs": echecs,
    }


def copier_depot(destination: Path) -> None:
    ignorer = shutil.ignore_patterns(
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".coverage",
        "htmlcov",
        "_tmp",
        "*.pyc",
    )
    shutil.copytree(RACINE, destination, ignore=ignorer, dirs_exist_ok=True)


def appliquer_mutation(depot: Path, mutation: dict) -> None:
    chemin = depot / mutation["fichier"]
    texte = chemin.read_text(encoding="utf-8")
    if texte.count(mutation["ancien"]) != 1:
        raise RuntimeError(f"mutation {mutation['id']} : motif introuvable ou ambigu")
    chemin.write_text(texte.replace(mutation["ancien"], mutation["nouveau"]), encoding="utf-8")


def controler_workflow(python: str) -> dict:
    """Lit tests.yml avec PyYAML et vérifie les exigences de la chaîne (déclencheurs, étapes)."""
    code = r"""
import json, sys, yaml
doc = yaml.safe_load(open(".github/workflows/tests.yml", encoding="utf-8"))
declencheurs = doc.get("on") or doc.get(True) or {}
job = next(iter(doc["jobs"].values()))
etapes = job["steps"]
commandes = " ".join(str(e.get("run", "")) for e in etapes)
print(json.dumps({
    "declencheurs": sorted(declencheurs),
    "runner": job["runs-on"],
    "python": next((e["with"]["python-version"] for e in etapes if "setup-python" in str(e.get("uses", ""))), None),
    "etapes": [e.get("name") for e in etapes],
    "ruff_check": "ruff check ." in commandes,
    "ruff_format": "ruff format --check ." in commandes,
    "pytest": "pytest" in commandes,
    "couverture_seuil_90": "--cov-fail-under=90" in commandes,
    "rapports_toujours_archives": any(
        "upload-artifact" in str(e.get("uses", "")) and e.get("if") == "always()" for e in etapes
    ),
    "demo_echec_declenchable": "echec_volontaire" in json.dumps(doc, default=str),
}, ensure_ascii=False))
"""
    resultat = subprocess.run(
        [python, "-c", code], cwd=RACINE, capture_output=True, text=True, check=False
    )
    if resultat.returncode != 0:
        return {"erreur": resultat.stderr.strip()[-400:]}
    return json.loads(resultat.stdout)


def fr(valeur) -> str:
    """Nombre au format français (virgule décimale)."""
    return str(valeur).replace(".", ",")


def extrait(sortie: str, lignes: int = 12) -> str:
    return "\n".join(sortie.splitlines()[-lignes:])


def main(argv: list[str] | None = None) -> None:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("--python", default=sys.executable, help="interpréteur à utiliser")
    analyseur.add_argument(
        "--venv-vierge",
        action="store_true",
        help="crée un environnement virtuel neuf, y installe requirements.txt et l'utilise",
    )
    analyseur.add_argument("--sans-mutations", action="store_true")
    arguments = analyseur.parse_args(argv)
    python = arguments.python
    dossier_venv: Path | None = None
    installation: dict | None = None
    if arguments.venv_vierge:
        dossier_venv = Path(tempfile.mkdtemp(prefix="venv_ci_"))
        creation = executer(sys.executable, ["-m", "venv", str(dossier_venv)], RACINE)
        if creation["code"] != 0:
            raise SystemExit(
                f"création de l'environnement virtuel impossible :\n{creation['sortie']}"
            )
        python = str(dossier_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        installation = executer(
            python,
            ["-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"],
            RACINE,
        )
        installation.update(
            id="0",
            titre="Installation des dépendances figées",
            commande="pip install -r requirements.txt",
        )
        print(
            f"[0] {installation['titre']} -> code {installation['code']} en {installation['duree_s']} s"
        )
        if installation["code"] != 0:
            raise SystemExit(f"installation impossible :\n{extrait(installation['sortie'], 20)}")
    try:
        _executer_chaine(arguments, python, installation)
    finally:
        if dossier_venv is not None:
            shutil.rmtree(dossier_venv, ignore_errors=True)


def _executer_chaine(arguments, python: str, installation: dict | None) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    (RACINE / "reports").mkdir(exist_ok=True)

    versions = subprocess.run(
        [python, "-c", "import sys; print(sys.version.split()[0])"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    outils = subprocess.run(
        [python, "-m", "pip", "list", "--format=freeze"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    versions_outils = ", ".join(
        ligne
        for ligne in outils.splitlines()
        if ligne.split("==")[0] in {"ruff", "pytest", "pytest-cov"}
    )

    etapes = []

    def etape(
        identifiant: str, titre: str, commande_affichee: str, arguments_python: list[str], **kw
    ):
        resultat = executer(python, arguments_python, RACINE, **kw)
        resultat.update(id=identifiant, titre=titre, commande=commande_affichee)
        etapes.append(resultat)
        print(f"[{identifiant}] {titre} -> code {resultat['code']} en {resultat['duree_s']} s")
        return resultat

    etape("1", "Analyse statique", "ruff check .", ["-m", "ruff", "check", "--no-cache", "."])
    etape(
        "2",
        "Formatage",
        "ruff format --check .",
        ["-m", "ruff", "format", "--check", "--no-cache", "."],
    )
    nominal = etape(
        "3",
        "Tests et couverture (seuil 90 %)",
        "pytest --cov=app --cov=ml --cov-fail-under=90 --junitxml=… --resultats-json=…",
        commande_pytest("reports/_tmp/ci_nominal"),
    )
    nominal["resume"] = resume_pytest(nominal["sortie"])
    echec_dossier = "reports/_tmp/ci_echec_volontaire"
    echec = etape(
        "4",
        "Même commande avec le test volontairement défaillant (DEMO_ECHEC=1)",
        "DEMO_ECHEC=1 pytest --cov=app --cov=ml --cov-fail-under=90 …",
        commande_pytest(echec_dossier),
        env_extra={"DEMO_ECHEC": "1"},
    )
    echec["resume"] = resume_pytest(echec["sortie"])

    mutations = []
    if not arguments.sans_mutations:
        for mutation in MUTATIONS:
            with tempfile.TemporaryDirectory(prefix="mutation_") as dossier:
                depot = Path(dossier) / "depot"
                copier_depot(depot)
                appliquer_mutation(depot, mutation)
                resultat = executer(python, ["-m", "pytest", "-q", "-p", "no:cacheprovider"], depot)
            resultat.update(mutation)
            resultat["resume"] = resume_pytest(resultat["sortie"])
            mutations.append(resultat)
            print(
                f"[{mutation['id']}] {mutation['description']} -> code {resultat['code']}, "
                f"{len(resultat['resume']['echecs'])} test(s) en échec"
            )

    workflow = controler_workflow(python)
    ecrire_rapport(python, versions, versions_outils, etapes, mutations, workflow, installation)
    print("rapport écrit :", SORTIE)


def ecrire_rapport(
    python, version_python, versions_outils, etapes, mutations, workflow, installation=None
) -> None:
    par_id = {e["id"]: e for e in etapes}
    nominal, echec = par_id["3"], par_id["4"]
    lignes = [
        "# Preuve d'exécution de la chaîne d'intégration continue (réplication locale)",
        "",
        f"Générée le {datetime.now(UTC):%Y-%m-%d %H:%M} UTC par `python -m scripts.preuve_ci`.",
        "",
        "> Ce document prouve que les commandes du workflow `.github/workflows/tests.yml` réussissent "
        "dans un environnement vierge et qu'elles échouent quand un test échoue. **L'exécution sur "
        "GitHub (runner `ubuntu-latest`) reste à réaliser après la publication du dépôt** : voir la "
        "section « Publier le dépôt » du README. L'URL du dépôt et celle de l'exécution doivent être "
        "ajoutées au rapport final.",
        "",
        "## 1. Environnement",
        "",
        f"- Python {version_python} ({platform.system()} {platform.release()})",
        f"- Outils : {versions_outils}",
        (
            "- Environnement virtuel créé pour l'occasion, dépendances installées depuis "
            "`requirements.txt` (versions figées), comme sur un runner vierge."
            if installation
            else f"- Interpréteur fourni par l'utilisateur : `{python}` (environnement non recréé)."
        ),
        "",
        "## 2. Chaîne nominale : tout doit réussir",
        "",
        "| Étape | Commande | Code de sortie | Durée (s) | Verdict |",
        "| :--- | :--- | ---: | ---: | :--- |",
    ]
    for e in ([installation] if installation else []) + etapes[:3]:
        lignes.append(
            f"| {e['id']}. {e['titre']} | `{e['commande']}` | {e['code']} | {fr(e['duree_s'])} | "
            f"{'**réussie**' if e['code'] == 0 else '**échec**'} |"
        )
    r = nominal["resume"]
    tableau_couverture = re.search(
        r"^(Name\s+Stmts.*?^TOTAL.*?)$", nominal["sortie"], flags=re.M | re.S
    )
    lignes += [
        "",
        f"Bilan de pytest : `{r['bilan']}` ; couverture totale : **{fr(r['couverture'])} %** ; "
        f"{r['seuil']}.",
        "",
        "Ruff est lancé avec `--no-cache` (aucun cache local), comme sur un runner vierge.",
        "",
        "```text",
        extrait(par_id["1"]["sortie"], 2),
        extrait(par_id["2"]["sortie"], 2),
        extrait(nominal["sortie"], 8),
        "```",
        "",
        "Couverture par module (pytest-cov, branches comprises) :",
        "",
        "```text",
        tableau_couverture.group(1)
        if tableau_couverture
        else "(tableau de couverture indisponible)",
        "```",
        "",
        "## 3. Un test défaillant bloque la chaîne",
        "",
        "Même commande que l'étape 3, avec `DEMO_ECHEC=1` (variable positionnée par le déclenchement "
        "manuel du workflow, entrée `echec_volontaire`). Les rapports sont écrits dans un dossier temporaire "
        "pour ne pas écraser ceux de l'étape 3.",
        "",
        "| Commande | Code de sortie | Bilan | Test en échec | Verdict |",
        "| :--- | ---: | :--- | :--- | :--- |",
        f"| `{echec['commande']}` | {echec['code']} | `{echec['resume']['bilan']}` | "
        f"{', '.join('`' + t + '`' for t in echec['resume']['echecs']) or '—'} | "
        f"{'**le workflow échouerait (code ≠ 0)**' if echec['code'] != 0 else '**anomalie : aucun échec**'} |",
        "",
        "```text",
        extrait(echec["sortie"], 14),
        "```",
    ]
    if mutations:
        lignes += [
            "",
            "## 4. Un défaut introduit dans le code est détecté",
            "",
            "Chaque défaut est injecté seul dans une copie temporaire du dépôt ; la suite de tests est ensuite "
            "exécutée telle quelle. Une Pull Request contenant ce changement serait bloquée.",
            "",
            "| Id | Défaut injecté | Fichier | Code de sortie | Tests en échec | Verdict |",
            "| :--- | :--- | :--- | ---: | ---: | :--- |",
        ]
        for m in mutations:
            lignes.append(
                f"| {m['id']} | {m['description']} | `{m['fichier']}` | {m['code']} | "
                f"{len(m['resume']['echecs'])} | "
                f"{'**détecté**' if m['code'] != 0 else '**non détecté**'} |"
            )
        lignes.append("")
        for m in mutations:
            exemples = ", ".join(f"`{t.split('::')[-1]}`" for t in m["resume"]["echecs"][:4])
            lignes.append(f"- {m['id']} : {m['resume']['bilan']} ; par exemple {exemples or '—'}.")
    lignes += [
        "",
        f"## {'5' if mutations else '4'}. Contrôle statique du workflow",
        "",
        "```json",
        json.dumps(workflow, indent=1, ensure_ascii=False),
        "```",
        "",
        "## Ce qui reste à faire par l'étudiant",
        "",
        "1. Créer le dépôt GitHub `CreditRisk-Test`, pousser le code (README, section « Publier le dépôt »).",
        "2. Ouvrir une Pull Request : le workflow doit réussir (coche verte).",
        "3. Déclencher manuellement le workflow avec `echec_volontaire = true` : il doit échouer (croix rouge).",
        "4. Reporter dans le rapport final l'URL du dépôt et celles des deux exécutions (captures d'écran).",
        "",
    ]
    SORTIE.write_text("\n".join(lignes), encoding="utf-8")


if __name__ == "__main__":
    main()
