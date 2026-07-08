"""Statistical engine: per-subject percentile curves + joint WUM-index distribution.

Design, stated plainly (no black box):

1. MARGINAL per subject. Each subject's score(%)->percentile curve is the empirical
   CDF reconstructed from the official stanine table (see cke_data). We interpolate
   linearly between the published stanine boundaries. This respects the real skew of
   each subject far better than a mean/SD normal would (e.g. matematyka R is heavily
   right-skewed: modal 0, mean 33). To *sample* a subject we invert this curve.

2. JOINT across the WUM subjects. The candidate's rank on the recruitment index
   (sum of subjects) depends on how the subjects co-move — a fact CKE does NOT
   publish (no joint distribution). We combine the marginals with a Student-t copula
   whose correlation matrix and degrees-of-freedom nu are explicit, tunable assumptions
   (medical candidates' biology & chemistry correlate strongly; mathematics less so).
   The t copula has NON-zero upper-tail dependence (unlike a Gaussian copula, whose
   upper-tail dependence is exactly zero), so candidates who are high in ALL subjects
   co-occur — which is precisely the region a top-3% admission cut-off lives in. Lower
   nu => heavier joint tails; nu -> infinity recovers the Gaussian copula. Both the
   correlation and nu are parameters you can and should stress-test.

3. 2026 WITHOUT 2026 distributions. We shift each 2025 marginal horizontally by the
   change in its mean (e.g. biologia mean 46->41 => shift -5 pts), clipped to [0,100].
   This preserves the published *shape* while reproducing the announced mean drop, and
   is exactly the signature of a larger, weaker cohort. Cohort growth (+30%) does not
   move a percentile (it is scale-free) but scales the absolute number of rivals, which
   we report separately.

Everything is numpy-only (no scipy): the normal CDF uses math.erf and the Student-t CDF
uses a small vectorised regularized-incomplete-beta routine (continued fraction) below,
so we keep the module's zero-scipy contract while gaining t-copula tail dependence.
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


# --- regularized incomplete beta + Student-t CDF, vectorised, no scipy ----
def _betacf(a: float, b: float, x: np.ndarray, itmax: int = 300, eps: float = 1e-12):
    """Continued fraction for the incomplete beta (Lentz's method), vectorised over x."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    tiny = 1e-30
    c = np.ones_like(x)
    d = 1.0 - qab * x / qap
    d = np.where(np.abs(d) < tiny, tiny, d)
    d = 1.0 / d
    h = d.copy()
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d;  d = np.where(np.abs(d) < tiny, tiny, d);  d = 1.0 / d
        c = 1.0 + aa / c;  c = np.where(np.abs(c) < tiny, tiny, c)
        h = h * d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d;  d = np.where(np.abs(d) < tiny, tiny, d);  d = 1.0 / d
        c = 1.0 + aa / c;  c = np.where(np.abs(c) < tiny, tiny, c)
        de = d * c
        h = h * de
        if np.all(np.abs(de - 1.0) < eps):
            break
    return h


def _betai(a: float, b: float, x: np.ndarray) -> np.ndarray:
    """Regularized incomplete beta I_x(a, b), vectorised over x in [0,1]."""
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    lbt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
           + a * np.log(np.where(x <= 0, 1.0, x))
           + b * np.log(np.where(x >= 1, 1.0, 1.0 - x)))
    bt = np.exp(lbt)
    thresh = (a + 1.0) / (a + b + 2.0)
    direct = x < thresh
    # feed each branch only values in its convergent region; the other lane is unused
    x_d = np.where(direct, x, 0.5 * thresh)
    x_s = np.where(direct, 0.5 * thresh, x)
    cf_d = _betacf(a, b, x_d)
    cf_s = _betacf(b, a, 1.0 - x_s)
    res = np.where(direct, bt * cf_d / a, 1.0 - bt * cf_s / b)
    res = np.where(x <= 0, 0.0, res)
    res = np.where(x >= 1, 1.0, res)
    return res


def _t_cdf(t: np.ndarray, nu: float) -> np.ndarray:
    """CDF of a Student-t with `nu` degrees of freedom, vectorised. No scipy."""
    t = np.asarray(t, float)
    x = nu / (nu + t * t)                 # in (0,1]; ->1 as t->0, ->0 as |t|->inf
    ib = _betai(nu / 2.0, 0.5, x)         # I_x(nu/2, 1/2)
    lower = 0.5 * ib
    return np.where(t <= 0, lower, 1.0 - lower)


# --- empirical marginal from stanine curve --------------------------------
class Marginal:
    """Empirical score(%)<->percentile curve for one subject, from its stanine table.

    shift: pts added to every score knot (for modelling a weaker/stronger year),
           clipped into [0,100] with monotonicity preserved.
    tilt_shift: a *conditioning / reweight* of the empirical distribution onto a
           sub-population whose mean is `tilt_shift` points higher (or lower). Unlike a
           rigid `shift`, this keeps the same support [0,100] (no boundary pile-up): it
           exponentially tilts the stanine-segment masses (max-entropy reweight matching
           the target mean) so both the CDF (`percentile`) and sampling (`quantile`)
           reflect the sub-population consistently. Used to turn a national subject
           marginal into a med-applicant-pool marginal for the third WUM slot (see
           cke_data.THIRD_MEDPOOL_GAP and wum.analyse_year).
    """
    def __init__(self, stats: SubjectStats, shift: float = 0.0, tilt_shift: float = 0.0):
        self.stats = stats
        self.shift = shift
        self.tilt_shift = tilt_shift
        self.theta = 0.0
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
        if tilt_shift:
            self._apply_tilt(tilt_shift)

    def _apply_tilt(self, gap: float) -> None:
        """Exponentially tilt the segment masses so the mean moves by `gap` points.

        Segment i (between knots x_i, x_{i+1}) carries base mass m_i at midpoint mid_i.
        Reweight m'_i ∝ m_i·exp(theta·mid_i), renormalised, and solve theta so the new
        mean equals base_mean + gap. mean(theta) is monotone increasing in theta, so a
        bisection is robust. The target is clamped to the achievable (min,max) midpoint.
        """
        x = self._s
        mass = np.diff(self._c)
        mid = (x[:-1] + x[1:]) / 2.0
        base = float(np.sum(mass * mid))
        lo_m, hi_m = float(mid.min()), float(mid.max())
        target = min(max(base + gap, lo_m + 1e-6), hi_m - 1e-6)
        c0 = float(mid.mean())   # center for numerical stability

        def weights(theta):
            z = theta * (mid - c0)
            z = z - z.max()               # log-sum-exp stability (avoid exp overflow)
            w = mass * np.exp(z)
            return w / w.sum()

        lo, hi = -50.0, 50.0
        for _ in range(100):
            mt = 0.5 * (lo + hi)
            if float(np.sum(weights(mt) * mid)) < target:
                lo = mt
            else:
                hi = mt
        self.theta = 0.5 * (lo + hi)
        w = weights(self.theta)
        self._c = np.concatenate([[0.0], np.cumsum(w)])

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
    index_samples: np.ndarray          # simulated recruitment-index scores
    subjects: list                     # subject order
    corr: np.ndarray                   # correlation matrix used
    nu: float | None = None            # Student-t dof (None = Gaussian copula)
    subject_samples: np.ndarray | None = None   # (n, k) per-subject sampled scores

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
                   n: int = 200_000, seed: int = 12345, nu: float | None = 6.0,
                   combine=None) -> JointResult:
    """Monte-Carlo the joint distribution of the recruitment index.

    Copula step (dependence):
      * draw correlated standard normals  X = Z·Lᵀ  (R = L·Lᵀ);
      * if `nu` is set, divide by sqrt(W/nu) with W ~ chi2(nu) to make X multivariate-t,
        then map to uniforms with the Student-t CDF  U = t_nu(X)  — a *t copula*, which
        has non-zero upper-tail dependence (candidates high in all subjects co-occur);
      * if `nu` is None, map with the normal CDF  U = Phi(X)  — the Gaussian copula
        (zero upper-tail dependence), recovered in the limit nu -> infinity.
    Marginals are unchanged: invert each subject's empirical CDF, U_j -> score_j.

    combine: optional callable (cols[n,k], subjects) -> index[n]. Default = row sum.
             WUM uses it to take chem + bio + max(math, phys) (an order statistic on the
             third slot), which a single summed marginal cannot express.
    """
    subs = [m.stats.subject for m in marginals]
    R = default_corr(subs) if corr is None else np.asarray(corr, float)
    L = _nearest_psd_cholesky(R)
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal((n, len(marginals))) @ L.T
    if nu is None:
        U = _norm_cdf(Z)
    else:
        W = rng.chisquare(nu, size=(n, 1))
        T = Z / np.sqrt(W / nu)
        U = _t_cdf(T, nu)
    cols = np.column_stack([m.sample(U[:, j]) for j, m in enumerate(marginals)])
    index = cols.sum(axis=1) if combine is None else np.asarray(combine(cols, subs), float)
    return JointResult(index_samples=index, subjects=subs, corr=R, nu=nu,
                       subject_samples=cols)
