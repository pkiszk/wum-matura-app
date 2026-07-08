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

import numpy as np

from cke_data import YearData, load_2025
from model import Marginal, simulate_index, default_corr, JointResult

# WUM index: chemia + biologia + best-of(matematyka, fizyka). Third slot configurable.
WUM_CORE = ("chemia", "biologia")
WUM_THIRD_DEFAULT = "matematyka"     # or "fizyka"
# 4-var copula order for the max(math, phys) model: chem, bio, and BOTH third options.
WUM_SUBJECTS_4 = ("chemia", "biologia", "matematyka", "fizyka")


def wum_corr(r_bc: float, r_b3: float, r_c3: float, r_mf: float = 0.60) -> np.ndarray:
    """Build the 4x4 correlation over [chemia, biologia, matematyka, fizyka] from the
    three core sliders (bio-chem, bio-third, chem-third). The third-slot correlations
    are applied to BOTH matematyka and fizyka; r_mf is math<->phys (rarely co-taken, so
    it only shapes the latent max)."""
    return np.array([
        [1.0,  r_bc, r_c3, r_c3],
        [r_bc, 1.0,  r_b3, r_b3],
        [r_c3, r_b3, 1.0,  r_mf],
        [r_c3, r_b3, r_mf, 1.0]], float)


def _max_third_combine(cols: np.ndarray, subs: list) -> np.ndarray:
    """WUM index on 4-var samples: chem + bio + max(math, phys)."""
    ix = {s: k for k, s in enumerate(subs)}
    best_third = np.maximum(cols[:, ix["matematyka"]], cols[:, ix["fizyka"]])
    return cols[:, ix["chemia"]] + cols[:, ix["biologia"]] + best_third


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
                                       # (third slot = MED-POOL marginal, not national)
    pool: float                        # relevant applicant-pool size assumed
    rank_above: float                  # estimated rivals scoring strictly higher
    note: str = ""
    extras: dict = field(default_factory=dict)   # nu, med-pool gap, national third %ile…


def _subject_order(third: str) -> list[str]:
    return [WUM_CORE[0], WUM_CORE[1], third]


def analyse_year(data: YearData, candidate: Candidate, *, third: str = WUM_THIRD_DEFAULT,
                 corr=None, pool: float | None = None, shifts: dict | None = None,
                 n: int = 200_000, seed: int = 12345, nu: float | None = 6.0,
                 medpool: bool = True, max_third: bool = True,
                 medpool_gap: dict | None = None, note: str = "") -> YearAnalysis:
    """Run the full analysis for one year's population against one candidate.

    shifts:    optional {subject: pts} horizontal shift applied to that subject's
               marginal (models 2026 as the 2025 shape moved by the announced mean change).
    nu:        Student-t copula degrees of freedom (None = Gaussian). Lower => heavier
               joint tails / more upper-tail dependence where the cut-off lives.
    medpool:   reweight the THIRD-slot marginal(s) onto the med-applicant sub-population
               (national maths/physics R is not the right reference — see cke_data).
    max_third: model the third slot as max(matematyka, fizyka) via a 4-var copula (the
               real WUM rule) instead of a single chosen marginal.
    pool:      relevant applicant-pool size. Default = N of the rarest core subject
               (chemia), the binding constraint for a med-school triple.
    """
    shifts = shifts or {}

    def _marg(subject, is_third):
        gap = data.medpool_gap_for(subject) if (medpool and is_third) else 0.0
        if medpool_gap and subject in medpool_gap and is_third:
            gap = float(medpool_gap[subject])
        return Marginal(data.get(subject), shift=shifts.get(subject, 0.0), tilt_shift=gap)

    core = {s: _marg(s, is_third=False) for s in WUM_CORE}

    if max_third:
        third_marg = {s: _marg(s, is_third=True) for s in ("matematyka", "fizyka")}
        marginals = {**core, **third_marg}
        order = list(WUM_SUBJECTS_4)                    # chem, bio, math, phys
        R = default_corr(order) if corr is None else corr
        joint = simulate_index([marginals[s] for s in order], corr=R, n=n, seed=seed,
                               nu=nu, combine=_max_third_combine)
    else:
        marginals = {**core, third: _marg(third, is_third=True)}
        order = _subject_order(third)
        joint = simulate_index([marginals[s] for s in order], corr=corr, n=n, seed=seed, nu=nu)

    # Candidate keeps their OWN chosen third subject (they did not sit the other one);
    # the FIELD gets the max(math, phys) uplift, so the candidate ranks slightly lower.
    report_subjects = _subject_order(third)
    idx = candidate.index(report_subjects)
    pct = joint.percentile_of(idx)

    # Per-subject standing: chem/bio vs national; third vs the MED-POOL marginal.
    subj_pct = {s: marginals[s].percentile(candidate.scores[s]) for s in report_subjects}
    third_national_pct = Marginal(
        data.get(third), shift=shifts.get(third, 0.0)).percentile(candidate.scores[third])

    if pool is None:
        pool = float(data.get("chemia").n)
    above = joint.rank_above(idx, pool)
    extras = {"nu": nu, "medpool": medpool, "max_third": max_third,
              "third": third,
              "third_medpool_gap": (data.medpool_gap_for(third) if medpool else 0.0),
              "third_national_pct": third_national_pct,
              "third_medpool_pct": subj_pct[third]}
    return YearAnalysis(year=data.year, subjects=report_subjects, joint=joint,
                        marginals=marginals, candidate_index=idx, candidate_percentile=pct,
                        candidate_subject_pct=subj_pct, pool=pool, rank_above=above,
                        note=note, extras=extras)


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
