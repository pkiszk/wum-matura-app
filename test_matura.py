"""Sanity/acceptance tests for the matura percentile module. Run:
    python3 src/matura/test_matura.py     # must print ALL PASS
No network. Locks the engine to hand-checkable facts about the 2025 stanine data.
"""
from __future__ import annotations
import sys, pathlib, dataclasses
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np

from cke_data import (load_2025, DATA_2025, STANINE_BANDS, dump_template, load_year,
                      THIRD_MEDPOOL_GAP)
from model import Marginal, simulate_index, _norm_cdf, _t_cdf
from wum import Candidate, analyse_year, build_2026, default_candidate, project_cutoff

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <-- ' + detail}")
    if not cond:
        FAILS.append(name)


def _find_2026():
    """Locate 2026.json across layouts: flat deploy repo (root) or AICF (src/matura)."""
    here = pathlib.Path(__file__).resolve().parent
    for p in (here / "2026.json",                                   # flat deploy repo
              here.parents[1] / "data" / "matura" / "2026.json",    # some nested layouts
              here.parents[2] / "data" / "matura" / "2026.json"):   # AICF: src/matura -> root
        if p.exists():
            return p
    raise FileNotFoundError("2026.json not found next to tests or in data/matura")


def _scratch(name):
    """A writable temp path next to the test file (works in any layout)."""
    return pathlib.Path(__file__).resolve().parent / name


def test_stanine_bands_sum():
    check("stanine bands sum to 1.00", abs(sum(STANINE_BANDS) - 1.0) < 1e-9)


def test_marginal_reproduces_stanine_boundaries():
    """The stanine FALLBACK machinery: at each stanine upper bound the CDF must equal the
    cumulative band fraction. chemia now ships a finer centyle curve, so strip it to test
    the fallback path explicitly."""
    st = dataclasses.replace(DATA_2025["chemia"], centile=())   # stanine-only
    m = Marginal(st)
    s, c = st.cdf_knots()
    ok = all(abs(m.percentile(si) - ci * 100) < 1e-6 for si, ci in zip(s, c))
    check("chemia stanine CDF hits every stanine boundary", ok)
    # chemia: 80% is top of stanine 7 -> cumulative 0.89
    check("chemia stanine 80% -> ~89th pct", abs(m.percentile(80) - 89.0) < 1e-6,
          f"got {m.percentile(80):.2f}")


def test_marginal_reproduces_centile_curve():
    """The PRIMARY empirical object: with the published centyle curve, percentile(score)
    must equal the published centyl at every knot, and beat the coarse stanine object."""
    st = DATA_2025["chemia"]
    check("chemia ships a centyle curve", len(st.centile) > 30)
    m = Marginal(st)
    ok = all(abs(m.percentile(float(sc)) - float(pc)) < 1e-6 for sc, pc in st.centile)
    check("chemia CDF hits every published centyl knot", ok)
    # chemia 2025: 80% -> centyl 90 (finer than the 89 the stanine object returns)
    check("chemia centyle 80% -> 90th pct", abs(m.percentile(80) - 90.0) < 1e-6,
          f"got {m.percentile(80):.2f}")
    stan = Marginal(dataclasses.replace(st, centile=()))
    check("centyle and stanine disagree at 80 (finer curve)",
          abs(m.percentile(80) - stan.percentile(80)) > 0.5)


def test_marginal_monotone_and_bounded():
    for key, st in DATA_2025.items():
        m = Marginal(st)
        xs = np.linspace(0, 100, 101)
        p = np.array([m.percentile(x) for x in xs])
        check(f"{key} CDF monotone non-decreasing", np.all(np.diff(p) >= -1e-9))
        check(f"{key} percentile in [0,100]", p.min() >= -1e-9 and p.max() <= 100 + 1e-9)
        # inverse consistency: quantile(percentile(x)) ~ x on the interior
        u = m.percentile(50) / 100
        check(f"{key} quantile inverts CDF near median",
              abs(m.quantile(np.array([u]))[0] - 50) < 3.0, f"{m.quantile(np.array([u]))[0]:.1f}")


def test_norm_cdf():
    check("norm_cdf(0)=0.5", abs(_norm_cdf(np.array([0.0]))[0] - 0.5) < 1e-9)
    check("norm_cdf(1.96)~0.975", abs(_norm_cdf(np.array([1.96]))[0] - 0.975) < 1e-3)


def test_candidate_index_and_percentile():
    d = load_2025(); cand = default_candidate()
    an = analyse_year(d, cand, n=100_000)
    check("candidate index == 245", abs(an.candidate_index - 245) < 1e-9)
    # chem/bio ranked vs national via the published 2025 centyle curve: chem 85 -> 94,
    # bio 88 -> 98 (exact centyl knots).
    check("chem 85 -> 94 pct (centyle)", abs(an.candidate_subject_pct["chemia"] - 94.0) < 0.3,
          f"{an.candidate_subject_pct['chemia']:.2f}")
    check("bio 88 -> 98 pct (centyle)", abs(an.candidate_subject_pct["biologia"] - 98.0) < 0.3,
          f"{an.candidate_subject_pct['biologia']:.2f}")
    # the THIRD subject reports the MED-POOL percentile (see test_medpool_third_delta);
    # the national centyl (91 in 2025) is kept in extras for context.
    check("math 72 national -> 91 pct (2025 centyle, extras)",
          abs(an.extras["third_national_pct"] - 91.0) < 0.3,
          f"{an.extras['third_national_pct']:.2f}")
    check("math 72 med-pool pct materially below national (default model)",
          an.candidate_subject_pct["matematyka"] < an.extras["third_national_pct"] - 8,
          f"{an.candidate_subject_pct['matematyka']:.2f}")
    # med-pool third + max(math,phys) + t-copula keep the index below the old raw-national
    # 96.3% — a top band, not the top ~2%.
    check("index 245 percentile in a sane high band (89-96)",
          89 <= an.candidate_percentile <= 96, f"{an.candidate_percentile:.2f}")


def test_t_cdf_matches_reference():
    """Student-t CDF (our no-scipy incomplete-beta routine) vs hand references."""
    refs = [(0.0, 5, 0.5), (2.0, 5, 0.9490), (1.0, 10, 0.8296),
            (-2.0, 8, 0.0403), (3.0, 3, 0.9711)]
    for t, nu, ref in refs:
        got = float(_t_cdf(np.array([t]), nu)[0])
        check(f"t_cdf({t:+.0f}, nu={nu}) ~ {ref}", abs(got - ref) < 2e-3, f"{got:.4f}")
    # limiting behaviour
    check("t_cdf(+8, nu=6) ~ 1", _t_cdf(np.array([8.0]), 6)[0] > 0.999)
    check("t_cdf monotone", _t_cdf(np.array([-1.0]), 6)[0] < _t_cdf(np.array([1.0]), 6)[0])


def test_medpool_third_delta():
    """CHANGE 1: the third subject ranked against the med pool, not the national pool.

    matematyka 72 vs the raw national centyle curve reads 91% (2025) / 87% (2026); vs the
    med-pool marginal it drops materially — because national maths-R is diluted by non-med
    candidates. Documents the delta the fix produces.
    """
    d25, cand = load_2025(), default_candidate()
    d26 = load_year(_find_2026())
    check("matematyka has a med-pool gap defined", THIRD_MEDPOOL_GAP.get("matematyka", 0) > 0)

    for label, d, nat_ref in [("2025", d25, 91.0), ("2026", d26, 87.0)]:
        an = analyse_year(d, cand, n=200_000)
        nat = an.extras["third_national_pct"]
        mp = an.extras["third_medpool_pct"]
        check(f"{label} matematyka national %ile ~ {nat_ref}", abs(nat - nat_ref) < 0.6,
              f"{nat:.2f}")
        check(f"{label} matematyka med-pool %ile materially below national (delta > 8)",
              nat - mp > 8, f"nat={nat:.1f} medpool={mp:.1f} delta={nat-mp:.1f}")
        # a rightward-reweighted pool cannot lift a fixed score's percentile
        check(f"{label} med-pool %ile <= national %ile", mp <= nat + 1e-6,
              f"nat={nat:.1f} medpool={mp:.1f}")
        # disabling med-pool recovers the national figure exactly
        an_nat = analyse_year(d, cand, n=200_000, medpool=False)
        check(f"{label} medpool=False recovers national third %ile",
              abs(an_nat.candidate_subject_pct["matematyka"] - nat) < 1e-6,
              f"{an_nat.candidate_subject_pct['matematyka']:.2f}")


def test_student_t_upper_tail_monotone_in_nu():
    """CHANGE 2: lower nu (heavier joint tails) raises the index upper-tail density, and
    the projected cut-off moves up. Gaussian copula (nu=None) is the light-tail limit."""
    d, cand = load_2025(), default_candidate()
    nus = [3, 8, 40, None]
    p99 = [np.percentile(analyse_year(d, cand, n=200_000, nu=nu).joint.index_samples, 99)
           for nu in nus]
    check("index p99 strictly decreasing as nu rises (3 > 8 > 40 > Gaussian)",
          all(p99[i] > p99[i + 1] for i in range(len(p99) - 1)),
          f"{[round(x, 1) for x in p99]}")
    check("t(nu=3) upper tail clearly above Gaussian (>2 pts at p99)",
          p99[0] - p99[-1] > 2.0, f"{p99[0]-p99[-1]:.2f}")
    # projected 2026 cut-off inherits the tail: heavier tail (low nu) => higher cut
    d26 = load_year(_find_2026())
    def cut(nu):
        a25 = analyse_year(d, cand, pool=20340, n=200_000, nu=nu)
        a26 = analyse_year(d26, cand, pool=31691, n=200_000, nu=nu)
        return project_cutoff(a25, a26, cut_base=221, pool_base=20340, pool_target=31691)["cut_target"]
    c_lo, c_hi = cut(3), cut(None)
    check("projected cut-off higher under heavy tails (nu=3 >= Gaussian)",
          c_lo >= c_hi - 1e-6, f"nu3={c_lo:.2f} gauss={c_hi:.2f}")


def test_max_third_uplift():
    """CHANGE 3: modelling the third slot as max(math, phys) via a 4-var copula raises the
    field's mean and upper tail vs a single-third marginal, and lowers the candidate's
    percentile slightly (the candidate sat only maths; the field gets the best-of uplift)."""
    d, cand = load_2025(), default_candidate()
    single = analyse_year(d, cand, n=200_000, max_third=False)
    both = analyse_year(d, cand, n=200_000, max_third=True)
    s1, s2 = single.joint.index_samples, both.joint.index_samples
    check("max(math,phys) raises field index mean", s2.mean() > s1.mean() + 2,
          f"single={s1.mean():.1f} max={s2.mean():.1f}")
    check("max(math,phys) raises field index p99",
          np.percentile(s2, 99) > np.percentile(s1, 99),
          f"single={np.percentile(s1,99):.1f} max={np.percentile(s2,99):.1f}")
    check("candidate percentile falls under max-third",
          both.candidate_percentile < single.candidate_percentile,
          f"single={single.candidate_percentile:.2f} max={both.candidate_percentile:.2f}")


def test_2026_weaker_raises_percentile():
    d = load_2025(); cand = default_candidate()
    an25 = analyse_year(d, cand, n=100_000)
    shifts, pool26 = build_2026(d, means_2026={"biologia": 41, "chemia": 41}, growth=0.30)
    check("bio shift == -5", abs(shifts["biologia"] + 5) < 1e-9)
    check("chem shift == -2", abs(shifts["chemia"] + 2) < 1e-9)
    an26 = analyse_year(d, cand, shifts=shifts, pool=pool26, n=100_000)
    check("weaker 2026 cohort -> higher percentile for same score",
          an26.candidate_percentile >= an25.candidate_percentile - 1e-6,
          f"25={an25.candidate_percentile:.2f} 26={an26.candidate_percentile:.2f}")
    check("2026 pool == chemia N * 1.30", abs(pool26 - d.get("chemia").n * 1.30) < 1e-6)


def test_cutoff_projection():
    d = load_2025(); cand = default_candidate()
    an25 = analyse_year(d, cand, pool=20340, n=200_000)
    shifts, _ = build_2026(d, means_2026={"biologia": 41, "chemia": 41}, growth=0.0)
    an26 = analyse_year(d, cand, shifts=shifts, pool=31691, n=200_000)
    p = project_cutoff(an25, an26, cut_base=221, pool_base=20340, pool_target=31691)
    # identity: base==target dist & pool must reproduce the same cut-off
    same = project_cutoff(an25, an25, cut_base=221, pool_base=20340, pool_target=20340)
    check("no-change projection reproduces cut (~221)", abs(same["cut_target"] - 221) <= 2,
          f"{same['cut_target']:.1f}")
    # decomposition must add up to net
    check("pool_effect + weakening == net",
          abs((p["pool_effect"] + p["weakening_effect"]) - p["net"]) < 1e-6)
    # +56% pool with modest weakening => cut rises a few points
    check("projected 2026 cut in 225-234 band", 225 <= p["cut_target"] <= 234,
          f"{p['cut_target']:.1f}")
    check("pool effect positive, weakening effect negative",
          p["pool_effect"] > 0 and p["weakening_effect"] < 0,
          f"pool={p['pool_effect']:.1f} weak={p['weakening_effect']:.1f}")
    # more seats can only lower (or hold) the cut-off
    p_more = project_cutoff(an25, an26, cut_base=221, pool_base=20340, pool_target=31691,
                            seats_growth=0.20)
    check("more seats -> cut-off not higher", p_more["cut_target"] <= p["cut_target"] + 1e-6,
          f"{p_more['cut_target']:.1f} vs {p['cut_target']:.1f}")


def test_seed_reproducible():
    d = load_2025(); cand = default_candidate()
    a1 = analyse_year(d, cand, n=50_000, seed=7).candidate_percentile
    a2 = analyse_year(d, cand, n=50_000, seed=7).candidate_percentile
    check("same seed -> identical percentile", abs(a1 - a2) < 1e-12)


def test_json_roundtrip():
    p = _scratch("_test_tmpl.json")
    dump_template(p, year=2026)
    yd = load_year(p)
    check("template loads back with 4 subjects", len(yd.subjects) == 4)
    check("loaded chemia mean matches 2025 built-in", yd.get("chemia").mean == 43)
    p.unlink()


if __name__ == "__main__":
    print("MATURA MODULE TESTS")
    for fn in [test_stanine_bands_sum, test_marginal_reproduces_stanine_boundaries,
               test_marginal_reproduces_centile_curve,
               test_marginal_monotone_and_bounded, test_norm_cdf, test_t_cdf_matches_reference,
               test_candidate_index_and_percentile, test_medpool_third_delta,
               test_student_t_upper_tail_monotone_in_nu, test_max_third_uplift,
               test_2026_weaker_raises_percentile,
               test_cutoff_projection, test_seed_reproducible, test_json_roundtrip]:
        fn()
    print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}"))
    sys.exit(1 if FAILS else 0)
