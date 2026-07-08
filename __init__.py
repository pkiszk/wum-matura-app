"""Matura -> university-recruitment percentile module (standalone; unrelated to DCF).

Estimates where a WUM (Warsaw Medical University) candidate ranks, from official CKE
2025 extended-level distributions, with an explicit 2026 weaker/larger-cohort model.
"""
from cke_data import load_2025, load_year, YearData, SubjectStats  # noqa: F401
from model import Marginal, simulate_index                          # noqa: F401
from wum import (Candidate, analyse_year, build_2026,               # noqa: F401
                 default_candidate, WUM_CORE)
