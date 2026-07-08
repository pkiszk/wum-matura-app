"""Statistical engine: per-subject percentile curves + joint WUM-index distribution.

Design, stated plainly (no black box):

1. MARGINAL per subject. Each subject's score(%)->percentile curve is the empirical
   CDF reconstructed from the official stanine table (see cke_data). We interpolate
   linearly between the published stanine boundaries. This respects the real skew of
   each subject far better than a mean/SD normal would (e.g. matematyka R is heavily
   right-skewed: modal 0, mean 33). To *sample* a subject we invert this curve.

2. JOINT across the three WUM subjects. The candidate's rank on the recruitment index
   (sum of three subjects) depends on how the subjects co-move — a fact CKE does NOT
   publish (no joint distribution). We therefore combine the marginals with a Gaussian
   copula whose correlation matrix is an explicit, tunable assumption (medical
   candidates' biology & chemistry correlate strongly; mathematics less so). Higher
   correlation fattens the tails of the sum, which matters for a high scorer. The
   correlation is a parameter you can and should stress-test.

3. 2026 WITHOUT 2026 distributions. We shift each 2025 marginal horizontally by the
   change in its mean (e.g. biologia mean 46->41 => shift -5 pts), clipped to [0,100].
   This preserves the published *shape* while reproducing the announced mean drop, and
   is exactly the signature of a larger, weaker cohort. Cohort growth (+30%) does not
   move a percentile (it is scale-free) but scales the absolute number of rivals, which
   we report separately.

Everything is numpy-only (no scipy): the normal CDF uses math.erf.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np

from cke_data import SubjectStats


# --- normal CDF, vectorised, no scipy -------------------------------------
_SQRT2 = math.sqrt(2.0)
def _norm_cdf(x: np.ndarray) -> np.ndarray:
    # 0.5*(1+erf(x/sqrt2)); np.vectorize(math.erf) is fine at our sample sizes
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / _SQRT2))


# --- empirical marginal from stanine curve --------------------------------
class Marginal:
    """Empirical score(%)<->percentile curve for one subject, from its stanine table.

    shift: pts added to every score knot (for modelling a weaker/stronger year),
           clipped into [0,100] with monotonicity preserved.
    """
    def __init__(self, stats: SubjectStats, shift: float = 0.0):
        self.stats = stats
        self.shift = shift
        s, c = stats.cdf_knots()
        s = np.clip(np.asarray(s, float) + shift, 0.0, 100.0)
        c = np.asarray(c, float)
        # enforce strictly increasing score knots after clipping (merge ties, keep max cum)
        keep_s, keep_c = [s[0]], [c[0]]
        for si, ci in zip(s[1:], c[1:]):
            if si <= keep_s[-1]:
                keep_c[-1] = max(keep_c[-1], ci)
            else:
                keep_s.append(si); keep_c.append(ci)
        self._s = np.asarray(keep_s); self._c = np.asarray(keep_c)

    def percentile(self, score: float) -> float:
        """P(result <= score) * 100, i.e. the percentile of `score` in this subject."""
        return float(np.interp(score, self._s, self._c) * 100.0)

    def quantile(self, u: np.ndarray) -> np.ndarray:
        """Inverse CDF: map uniforms u in [0,1] to scores (%)."""
        return np.interp(u, self._c, self._s)

    def mean(self) -> float:
        """Exact mean of the piecewise-linear empirical distribution.

        Each CDF segment [x_i, x_{i+1}] carries mass (F_{i+1}-F_i) uniformly, so its
        conditional mean is the midpoint. Mean = Σ mass·midpoint.
        """
        x, c = self._s, self._c
        mass = np.diff(c)
        mid = (x[:-1] + x[1:]) / 2.0
        return float(np.sum(mass * mid))

    def median(self) -> float:
        """Score at the 50th percentile of the empirical curve."""
        return float(self.quantile(np.array([0.5]))[0])

    def sample(self, u: np.ndarray) -> np.ndarray:
        return self.quantile(u)


# --- joint index distribution via Gaussian copula -------------------------
@dataclass
class JointResult:
    index_samples: np.ndarray          # simulated sum-of-three scores
    subjects: list                     # subject order
    corr: np.ndarray                   # correlation matrix used

    def percentile_of(self, value: float) -> float:
        """Percentile of an index `value`: % of the population scoring <= it."""
        return float(np.mean(self.index_samples <= value) * 100.0)

    def rank_above(self, value: float, pool: float) -> float:
        """Estimated number of candidates in `pool` scoring strictly above `value`."""
        frac_above = float(np.mean(self.index_samples > value))
        return frac_above * pool

    def summary(self):
        s = self.index_samples
        return {"mean": float(s.mean()), "median": float(np.median(s)),
                "sd": float(s.std()), "p90": float(np.percentile(s, 90)),
                "p99": float(np.percentile(s, 99)), "max_possible": 100 * len(self.subjects)}


def default_corr(subjects: list[str]) -> np.ndarray:
    """Reasonable default correlations among extended science subjects (tunable).

    bio<->chem strong (0.60), each <-> math moderate (0.45), bio/chem/phys similar.
    """
    pair = {
        frozenset({"biologia", "chemia"}): 0.60,
        frozenset({"biologia", "matematyka"}): 0.45,
        frozenset({"chemia", "matematyka"}): 0.50,
        frozenset({"biologia", "fizyka"}): 0.45,
        frozenset({"chemia", "fizyka"}): 0.55,
        frozenset({"matematyka", "fizyka"}): 0.60,
    }
    n = len(subjects)
    R = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            r = pair.get(frozenset({subjects[i], subjects[j]}), 0.5)
            R[i, j] = R[j, i] = r
    return R


def _nearest_psd_cholesky(R: np.ndarray):
    """Cholesky, nudging tiny non-PSD matrices onto the PSD cone if needed."""
    try:
        return np.linalg.cholesky(R)
    except np.linalg.LinAlgError:
        w, V = np.linalg.eigh(R)
        w = np.clip(w, 1e-6, None)
        R2 = V @ np.diag(w) @ V.T
        d = np.sqrt(np.diag(R2))
        R2 = R2 / np.outer(d, d)
        return np.linalg.cholesky(R2)


def simulate_index(marginals: list[Marginal], corr: np.ndarray | None = None,
                   n: int = 200_000, seed: int = 12345) -> JointResult:
    """Monte-Carlo the joint distribution of the sum of subject scores.

    Gaussian copula: draw correlated standard normals, push through the normal CDF to
    get correlated uniforms, then invert each subject's empirical marginal.
    """
    subs = [m.stats.subject for m in marginals]
    R = default_corr(subs) if corr is None else np.asarray(corr, float)
    L = _nearest_psd_cholesky(R)
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal((n, len(marginals))) @ L.T
    U = _norm_cdf(Z)
    cols = [m.sample(U[:, j]) for j, m in enumerate(marginals)]
    index = np.sum(cols, axis=0)
    return JointResult(index_samples=index, subjects=subs, corr=R)
