"""Sanity/acceptance tests for the matura percentile module. Run:
    python3 src/matura/test_matura.py     # must print ALL PASS
No network. Locks the engine to hand-checkable facts about the 2025 stanine data.
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np

from cke_data import load_2025, DATA_2025, STANINE_BANDS, dump_template, load_year
from model import Marginal, simulate_index, _norm_cdf
from wum import Candidate, analyse_year, build_2026, default_candidate, project_cutoff

FAILS = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <-- ' + detail}")
    if not cond:
        FAILS.append(name)


def test_stanine_bands_sum():
    check("stanine bands sum to 1.00", abs(sum(STANINE_BANDS) - 1.0) < 1e-9)


def test_marginal_reproduces_stanine_boundaries():
    """At each stanine upper bound the CDF must equal the cumulative band fraction."""
    st = DATA_2025["chemia"]
    m = Marginal(st)
    s, c = st.cdf_knots()
    ok = all(abs(m.percentile(si) - ci * 100) < 1e-6 for si, ci in zip(s, c))
    check("chemia CDF hits every stanine boundary", ok)
    # chemia: 80% is top of stanine 7 -> cumulative 0.89
    check("chemia 80% -> ~89th pct", abs(m.percentile(80) - 89.0) < 1e-6,
          f"got {m.percentile(80):.2f}")


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
    # from stanine hand-calc: chem 85 ~92.5, bio 88 ~96.8, math 72 ~86.6
    check("chem 85 ~ 92.5 pct", abs(an.candidate_subject_pct["chemia"] - 92.5) < 0.5,
          f"{an.candidate_subject_pct['chemia']:.2f}")
    check("bio 88 ~ 96.8 pct", abs(an.candidate_subject_pct["biologia"] - 96.8) < 0.5,
          f"{an.candidate_subject_pct['biologia']:.2f}")
    check("math 72 ~ 86.6 pct", abs(an.candidate_subject_pct["matematyka"] - 86.6) < 0.5,
          f"{an.candidate_subject_pct['matematyka']:.2f}")
    check("index 245 percentile in a sane high band (94-99)",
          94 <= an.candidate_percentile <= 99, f"{an.candidate_percentile:.2f}")


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
    an25 = analyse_year(d, cand, pool=21200, n=200_000)
    shifts, _ = build_2026(d, means_2026={"biologia": 41, "chemia": 41}, growth=0.0)
    an26 = analyse_year(d, cand, shifts=shifts, pool=33000, n=200_000)
    p = project_cutoff(an25, an26, cut_base=221, pool_base=21200, pool_target=33000)
    # identity: base==target dist & pool must reproduce the same cut-off
    same = project_cutoff(an25, an25, cut_base=221, pool_base=21200, pool_target=21200)
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
    p_more = project_cutoff(an25, an26, cut_base=221, pool_base=21200, pool_target=33000,
                            seats_growth=0.20)
    check("more seats -> cut-off not higher", p_more["cut_target"] <= p["cut_target"] + 1e-6,
          f"{p_more['cut_target']:.1f} vs {p['cut_target']:.1f}")


def test_seed_reproducible():
    d = load_2025(); cand = default_candidate()
    a1 = analyse_year(d, cand, n=50_000, seed=7).candidate_percentile
    a2 = analyse_year(d, cand, n=50_000, seed=7).candidate_percentile
    check("same seed -> identical percentile", abs(a1 - a2) < 1e-12)


def test_json_roundtrip():
    p = pathlib.Path(__file__).resolve().parents[2] / "data" / "matura" / "_test_tmpl.json"
    dump_template(p, year=2026)
    yd = load_year(p)
    check("template loads back with 4 subjects", len(yd.subjects) == 4)
    check("loaded chemia mean matches 2025 built-in", yd.get("chemia").mean == 43)
    p.unlink()


if __name__ == "__main__":
    print("MATURA MODULE TESTS")
    for fn in [test_stanine_bands_sum, test_marginal_reproduces_stanine_boundaries,
               test_marginal_monotone_and_bounded, test_norm_cdf,
               test_candidate_index_and_percentile, test_2026_weaker_raises_percentile,
               test_cutoff_projection, test_seed_reproducible, test_json_roundtrip]:
        fn()
    print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}"))
    sys.exit(1 if FAILS else 0)
