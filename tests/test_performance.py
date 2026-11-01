"""Tests de performance légers (CPU standard). Mesures détaillées : scripts/benchmark_performance.py."""

from __future__ import annotations

import time

import numpy as np
import pytest

from app.preprocessing import construire_caracteristiques
from app.validation import valider_demande
from tests.scenarios import PAYLOAD_VALIDE

OBJECTIF_P95_API_MS = 200.0
OBJECTIF_P95_INFERENCE_MS = 20.0
OBJECTIF_DEBIT_REQ_S = 50.0

pytestmark = pytest.mark.performance


def p95(valeurs_ms: list[float]) -> float:
    return float(np.percentile(valeurs_ms, 95))


@pytest.mark.exigence("EX17")
def test_latence_d_inference_p95(service):
    x = construire_caracteristiques(valider_demande(PAYLOAD_VALIDE))
    for _ in range(20):
        service.predire(x)
    durees = []
    for _ in range(300):
        debut = time.perf_counter()
        service.predire(x)
        durees.append((time.perf_counter() - debut) * 1000)
    assert p95(durees) <= OBJECTIF_P95_INFERENCE_MS, f"P95 = {p95(durees):.2f} ms"


@pytest.mark.exigence("EX17")
def test_latence_api_p95_et_debit_minimal(client):
    for _ in range(10):
        client.post("/predict", json=PAYLOAD_VALIDE)
    durees = []
    debut_total = time.perf_counter()
    for _ in range(200):
        debut = time.perf_counter()
        assert client.post("/predict", json=PAYLOAD_VALIDE).status_code == 200
        durees.append((time.perf_counter() - debut) * 1000)
    debit = 200 / (time.perf_counter() - debut_total)
    assert p95(durees) <= OBJECTIF_P95_API_MS, f"P95 = {p95(durees):.1f} ms"
    assert debit >= OBJECTIF_DEBIT_REQ_S, f"débit = {debit:.0f} req/s"
