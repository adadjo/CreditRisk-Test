"""Expérience : délai d'inactivité des connexions persistantes (keep-alive) d'uvicorn.

Par défaut, uvicorn ferme une connexion inactive après 5 s (`--timeout-keep-alive`). Un client qui
réutilise la connexion juste à cet instant reçoit une fermeture ou une réinitialisation : c'est la
cause probable des rares échecs de statut 0 observés pendant la charge progressive. L'expérience le
montre de façon déterministe, avec des clients bruts et des temps d'inactivité calibrés.

Usage : python -m scripts.essai_keep_alive
"""

from __future__ import annotations

import socket
import threading
import time

from scripts.benchmark_performance import DOSSIER, _requete_http, choisir_coeurs, serveur_local
from scripts.profils import charger_profils

PORT = 8791
DELAIS_S = (3.0, 4.5, 4.9, 4.97, 5.0, 5.03, 5.1, 6.0)
ESSAIS = 5


def lire_statut(connexion: socket.socket) -> str | None:
    """Statut HTTP de la réponse, ou None si la connexion est fermée avant la réponse complète."""
    connexion.settimeout(5)
    donnees = b""
    while b"\r\n\r\n" not in donnees:
        morceau = connexion.recv(65536)
        if not morceau:
            return None
        donnees += morceau
    en_tete, _, corps = donnees.partition(b"\r\n\r\n")
    longueur = next(
        int(ligne.split(b":")[1])
        for ligne in en_tete.split(b"\r\n")
        if ligne.lower().startswith(b"content-length")
    )
    while len(corps) < longueur:
        morceau = connexion.recv(65536)
        if not morceau:
            return None
        corps += morceau
    return en_tete.split(b" ")[1].decode()


def essai(delai: float, requete: bytes, resultats: dict, cle: tuple[float, int]) -> None:
    with socket.create_connection(("127.0.0.1", PORT)) as connexion:
        connexion.sendall(requete)
        if lire_statut(connexion) != "200":
            resultats[cle] = "échec initial"
            return
        time.sleep(delai)
        try:
            connexion.sendall(requete)
            statut = lire_statut(connexion)
        except (ConnectionResetError, BrokenPipeError):
            resultats[cle] = "réinitialisée"
            return
        resultats[cle] = "réussie" if statut == "200" else "fermée"


def main() -> None:
    requete = _requete_http(charger_profils(1)[0])
    resultats: dict = {}
    coeur_serveur, _ = choisir_coeurs()
    with serveur_local(PORT, coeur_serveur):
        fils = [
            threading.Thread(target=essai, args=(delai, requete, resultats, (delai, i)))
            for delai in DELAIS_S
            for i in range(ESSAIS)
        ]
        for fil in fils:
            fil.start()
        for fil in fils:
            fil.join()
    lignes = [
        "Réutilisation d'une connexion persistante après une période d'inactivité",
        "(serveur uvicorn par défaut : --timeout-keep-alive 5)",
        "",
        "Inactivité (s) | requêtes réussies | connexion fermée ou réinitialisée",
        "---------------|-------------------|----------------------------------",
    ]
    for delai in DELAIS_S:
        issues = [resultats[(delai, i)] for i in range(ESSAIS)]
        reussies = issues.count("réussie")
        lignes.append(
            f"{delai:14.2f} | {reussies:>8d} sur {ESSAIS} | {ESSAIS - reussies:>10d} sur {ESSAIS}"
        )
    texte = "\n".join(lignes) + "\n"
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / "essai_keep_alive.txt").write_text(texte, encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    main()
