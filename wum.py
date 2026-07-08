"""WUM (Warszawski Uniwersytet Medyczny) recruitment-index analysis.

WUM ranks candidates on a sum of three EXTENDED subjects, each in %, where 1% = 1 point
(so the index runs 0..300):
        chemia R + biologia R + (matematyka R  OR  fizyka R)
Physics may substitute for mathematics. Our candidate used mathematics.

This module estimates where a given candidate sits — as a percentile and an estimated
rank — both in the 2025 reference population and in a modelled 2026 population that is
larger and weaker (see build_2026).
"""
from __future__ import annotations
from dataclasses import dataclass, field

from cke_data import YearData, load_2025
from model import Marginal, simulate_index, default_corr, JointResult

# WUM index: chemia + biologia + best-of(matematyka, fizyka). Third slot configurable.
WUM_CORE = ("chemia", "biologia")
WUM_THIRD_DEFAULT = "matematyka"     # or "fizyka"


@dataclass
class Candidate:
    scores: dict            # subject -> % (e.g. {"chemia":85,"biologia":88,"matematyka":72})
    year: int = 2026
    label: str = "candidate"

    def index(self, subjects: list[str]) -> float:
        return float(sum(self.scores[s] for s in subjects))


@dataclass
class YearAnalysis:
    year: int
    subjects: list
    joint: JointResult
    marginals: dict                    # subject -> Marginal
    candidate_index: float
    candidate_percentile: float        # percentile of the index in this population
    candidate_subject_pct: dict        # subject -> candidate's marginal percentile
    pool: float                        # relevant applicant-pool size assumed
    rank_above: float                  # estimated rivals scoring strictly higher
    note: str = ""


def _subject_order(third: str) -> list[str]:
    return [WUM_CORE[0], WUM_CORE[1], third]


def analyse_year(data: YearData, candidate: Candidate, *, third: str = WUM_THIRD_DEFAULT,
                 corr=None, pool: float | None = None, shifts: dict | None = None,
                 n: int = 200_000, seed: int = 12345, note: str = "") -> YearAnalysis:
    """Run the full analysis for one year's population against one candidate.

    shifts: optional {subject: pts} horizontal shift applied to that subject's marginal
            (used to model 2026 as the 2025 shape moved by the announced mean change).
    pool:   relevant applicant-pool size. Default = N of the rarest core subject
            (chemia), the binding constraint for a med-school triple.
    """
    subjects = _subject_order(third)
    shifts = shifts or {}
    marginals = {s: Marginal(data.get(s), shift=shifts.get(s, 0.0)) for s in subjects}
    joint = simulate_index([marginals[s] for s in subjects], corr=corr, n=n, seed=seed)

    idx = candidate.index(subjects)
    pct = joint.percentile_of(idx)
    subj_pct = {s: marginals[s].percentile(candidate.scores[s]) for s in subjects}

    if pool is None:
        pool = float(data.get("chemia").n)
    above = joint.rank_above(idx, pool)
    return YearAnalysis(year=data.year, subjects=subjects, joint=joint, marginals=marginals,
                        candidate_index=idx, candidate_percentile=pct,
                        candidate_subject_pct=subj_pct, pool=pool, rank_above=above, note=note)


def build_2026(base: YearData, *, means_2026: dict, growth: float = 0.30) -> tuple[dict, float]:
    """Translate announced 2026 means into per-subject horizontal shifts + a pool.

    means_2026: {subject: new_mean_%} for whichever subjects changed. Shift = new-old.
    growth: fractional cohort growth vs 2025 (e.g. 0.30 == +30%). Scales the pool.
    Returns (shifts, pool_2026).
    """
    shifts = {}
    for s, m in means_2026.items():
        shifts[s] = float(m) - float(base.get(s).mean)
    pool_2026 = float(base.get("chemia").n) * (1.0 + growth)
    return shifts, pool_2026


def project_cutoff(base: YearAnalysis, target: YearAnalysis, cut_base: float,
                   pool_base: float, pool_target: float, seats_growth: float = 0.0) -> dict:
    """Project next year's admission cut-off (próg) from this year's.

    Logic: a cut-off is the score of the last admitted candidate, i.e. the number of
    people scoring >= cut equals the number of seats. We (1) read how many of the base-
    year pool beat `cut_base` -> implied seats (held fixed, optionally grown), then
    (2) find the score in the TARGET-year distribution at that same headcount from the
    top. Two opposing forces are separated: a larger pool pushes the cut UP (more rivals,
    same seats), a weaker distribution pulls it DOWN.

    Returns cut_target plus a decomposition (pool_effect vs weakening_effect).
    """
    import numpy as np
    s_base = base.joint.index_samples
    s_tgt = target.joint.index_samples
    frac_base = float((s_base >= cut_base).mean())      # 2025 in-pool admit rate
    seats = pool_base * frac_base * (1.0 + seats_growth)
    admit_target = min(max(seats / pool_target, 1e-9), 1 - 1e-9)
    cut_target = float(np.quantile(s_tgt, 1.0 - admit_target))
    cut_poolonly = float(np.quantile(s_base, 1.0 - admit_target))  # bigger pool, base shape
    return {"cut_base": cut_base, "cut_target": cut_target,
            "frac_base": frac_base, "seats": seats,
            "admit_base": frac_base, "admit_target": admit_target,
            "pool_effect": cut_poolonly - cut_base,          # from pool growth (+seats)
            "weakening_effect": cut_target - cut_poolonly,   # from weaker distribution
            "net": cut_target - cut_base}


def default_candidate() -> Candidate:
    """The candidate from the brief: chem 85, bio 88, math 72 => 245 pts, matura 2026."""
    return Candidate(scores={"chemia": 85, "biologia": 88, "matematyka": 72},
                     year=2026, label="245-pt candidate")
