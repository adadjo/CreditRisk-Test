"""Test volontairement défaillant : preuve que la CI bloque une Pull Request dont un test échoue.

Désactivé par défaut (le test est ignoré). Il s'active avec DEMO_ECHEC=1, soit en local,
soit via le déclenchement manuel du workflow (entrée « echec_volontaire »).
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.echec_volontaire
@pytest.mark.exigence("EX18")
@pytest.mark.skipif(os.getenv("DEMO_ECHEC") != "1", reason="actif seulement avec DEMO_ECHEC=1")
def test_echec_volontaire_pour_verifier_que_la_ci_bloque():
    assert False, (
        "Échec volontaire : le workflow doit être marqué en échec (code de sortie non nul)."
    )
