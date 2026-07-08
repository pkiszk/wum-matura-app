"""CLI report: estimate a WUM candidate's percentile from CKE 2025 data + 2026 model.

Run:
    python3 src/matura/report.py
    python3 src/matura/report.py --chem 85 --bio 88 --math 72
    python3 src/matura/report.py --third fizyka --phys 80
    python3 src/matura/report.py --data2026 data/matura/2026.json   # once real data exists

Leads with the takeaway, shows every intermediate number, cites the source population.
No black box: the 2026 result is a model (2025 shape shifted by announced mean drops),
clearly labelled as such.
"""
from __future__ import annotations
import sys, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cke_data import load_2025, load_year
from wum import Candidate, analyse_year, build_2026, project_cutoff, WUM_THIRD_DEFAULT


def _fmt_pct(x: float) -> str:
    return f"{x:.1f}%"


def main(argv=None):
    ap = argparse.ArgumentParser(description="WUM matura percentile estimator")
    ap.add_argument("--chem", type=float, default=85)
    ap.add_argument("--bio", type=float, default=88)
    ap.add_argument("--math", type=float, default=72)
    ap.add_argument("--phys", type=float, default=None,
                    help="physics %% (use with --third fizyka)")
    ap.add_argument("--third", choices=["matematyka", "fizyka"], default=WUM_THIRD_DEFAULT)
    ap.add_argument("--growth", type=float, default=0.56,
                    help="2026 pool growth vs 2025 = binding CHEMIA cohort growth "
                         "(20,340->31,691 this-year-graduates ~= +56%). NB overall matura "
                         "cohort grew ~+30%. (Mixing bases — e.g. 21,200->31,691 — wrongly "
                         "reads +49%; keep both years on the same CKE count.)")
    ap.add_argument("--bio2026", type=float, default=41.0, help="announced 2026 biologia mean")
    ap.add_argument("--chem2026", type=float, default=41.0, help="announced 2026 chemia mean")
    ap.add_argument("--pool", type=float, default=None, help="override 2025 applicant-pool size")
    ap.add_argument("--pool2026", type=float, default=None,
                    help="explicit 2026 pool (else 2025 pool x (1+growth))")
    ap.add_argument("--cut2025", type=float, default=None,
                    help="2025 admission cut-off (prog); enables the 2026 cut-off projection")
    ap.add_argument("--seats-growth", type=float, default=0.0,
                    help="assumed change in seats for the projection (e.g. 0.10 = +10%)")
    ap.add_argument("--data2026", type=str, default=None,
                    help="path to real 2026 JSON (bypasses the shift model)")
    ap.add_argument("--nu", type=float, default=6.0,
                    help="Student-t copula degrees of freedom (lower = heavier joint "
                         "tails / more upper-tail dependence). Use a large value or "
                         "--gaussian for the old Gaussian copula.")
    ap.add_argument("--gaussian", action="store_true",
                    help="use a Gaussian copula (nu -> infinity), zero upper-tail dependence")
    ap.add_argument("--no-medpool", action="store_true",
                    help="rank the third subject against the RAW national pool (overstates "
                         "the candidate; off by default)")
    ap.add_argument("--no-max-third", action="store_true",
                    help="model the third slot as a single subject instead of max(math,phys)")
    ap.add_argument("--n", type=int, default=200_000)
    a = ap.parse_args(argv)
    nu = None if a.gaussian else a.nu
    medpool = not a.no_medpool
    max_third = not a.no_max_third

    scores = {"chemia": a.chem, "biologia": a.bio}
    scores[a.third] = a.phys if (a.third == "fizyka" and a.phys is not None) else \
        (a.math if a.third == "matematyka" else (a.phys or 0))
    cand = Candidate(scores=scores, year=2026, label="candidate")
    idx = cand.index(["chemia", "biologia", a.third])

    d2025 = load_2025()
    print("=" * 74)
    print("WUM RECRUITMENT PERCENTILE  —  candidate index = "
          f"{idx:.0f} / 300  (chem {a.chem:.0f} + bio {a.bio:.0f} + {a.third} "
          f"{scores[a.third]:.0f})")
    print("=" * 74)

    cop = "Gaussian copula" if nu is None else f"Student-t copula (nu={nu:g})"
    print(f"\nModel: {cop}; third slot = "
          f"{'max(matematyka, fizyka)' if max_third else a.third} "
          f"(med-pool reference: {'ON' if medpool else 'OFF'}).")

    # ---- 2025 reference population -------------------------------------
    an25 = analyse_year(d2025, cand, third=a.third, pool=a.pool, n=a.n, nu=nu,
                        medpool=medpool, max_third=max_third,
                        note="Official CKE 2025 extended-level population.")
    print(f"\n[1] 2025 reference population  (all extended-level takers, N_chem="
          f"{d2025.get('chemia').n:,})")
    print(f"    Candidate per-subject percentile (chem/bio vs national; third vs med-pool):")
    for s in an25.subjects:
        st = d2025.get(s)
        tag = ""
        if s == a.third and medpool:
            tag = (f"  [MED-POOL; national would read "
                   f"{_fmt_pct(an25.extras['third_national_pct'])}, "
                   f"gap +{an25.extras['third_medpool_gap']:.0f} on the mean]")
        print(f"      {s:11s} {cand.scores[s]:5.0f}%  ->  "
              f"{_fmt_pct(an25.candidate_subject_pct[s]):>7}  "
              f"(subject mean {st.mean:.0f}%, sd {st.sd:.0f}%, N={st.n:,}){tag}")
    sm = an25.joint.summary()
    print(f"    Simulated index: mean {sm['mean']:.0f}, median {sm['median']:.0f}, "
          f"sd {sm['sd']:.0f}, p90 {sm['p90']:.0f}, p99 {sm['p99']:.0f} (max 300)")
    print(f"    >>> Index {idx:.0f} sits at the {_fmt_pct(an25.candidate_percentile)} "
          f"percentile of the 2025 pool.")
    print(f"        Est. rivals scoring higher in a pool of {an25.pool:,.0f}: "
          f"{an25.rank_above:,.0f}")

    # ---- 2026 modelled population -------------------------------------
    if a.data2026:
        d2026 = load_year(a.data2026)
        an26 = analyse_year(d2026, cand, third=a.third, n=a.n, nu=nu,
                            medpool=medpool, max_third=max_third,
                            note=f"Real 2026 data from {a.data2026}")
        pool_note = "real 2026 data"
    else:
        means = {"biologia": a.bio2026, "chemia": a.chem2026}
        shifts, pool26 = build_2026(d2025, means_2026=means, growth=a.growth)
        if a.pool2026 is not None:
            pool26 = a.pool2026
        an26 = analyse_year(d2025, cand, third=a.third, shifts=shifts, pool=pool26, n=a.n,
                            nu=nu, medpool=medpool, max_third=max_third,
                            note="MODEL: 2025 shape shifted by announced mean drops.")
        pool_note = (f"model: bio mean {d2025.get('biologia').mean:.0f}->{a.bio2026:.0f} "
                     f"({shifts['biologia']:+.0f}), chem {d2025.get('chemia').mean:.0f}->"
                     f"{a.chem2026:.0f} ({shifts['chemia']:+.0f}); cohort +{a.growth:.0%}")
    print(f"\n[2] 2026 population  ({pool_note})")
    sm2 = an26.joint.summary()
    print(f"    Simulated index: mean {sm2['mean']:.0f}, median {sm2['median']:.0f}, "
          f"sd {sm2['sd']:.0f}, p90 {sm2['p90']:.0f}, p99 {sm2['p99']:.0f}")
    print(f"    >>> Index {idx:.0f} sits at the {_fmt_pct(an26.candidate_percentile)} "
          f"percentile of the 2026 pool.")
    print(f"        Est. rivals scoring higher in a pool of {an26.pool:,.0f}: "
          f"{an26.rank_above:,.0f}")

    # ---- cut-off (próg) projection ------------------------------------
    proj = None
    if a.cut2025 is not None:
        proj = project_cutoff(an25, an26, cut_base=a.cut2025,
                              pool_base=an25.pool, pool_target=an26.pool,
                              seats_growth=a.seats_growth)
        print(f"\n[3] Admission cut-off (próg) projection")
        print(f"    2025 cut-off: {proj['cut_base']:.0f}  -> {proj['admit_base']*100:.1f}% of "
              f"the pool cleared it (~{proj['seats']:,.0f} admitted-equivalent seats"
              f"{'' if a.seats_growth==0 else f', +{a.seats_growth:.0%}'})")
        print(f"    2026 admit rate at fixed seats: {proj['admit_target']*100:.1f}%  "
              f"(pool {an25.pool:,.0f}->{an26.pool:,.0f})")
        print(f"    Decompose:  pool-growth pushes cut {proj['pool_effect']:+.0f}, "
              f"weaker field pulls {proj['weakening_effect']:+.0f}")
        print(f"    >>> Projected 2026 cut-off: {proj['cut_target']:.0f}  "
              f"({proj['net']:+.0f} vs 2025)")
        print(f"        Candidate {idx:.0f}: margin over 2025 cut {idx-proj['cut_base']:+.0f}, "
              f"over projected 2026 cut {idx-proj['cut_target']:+.0f}")

    # ---- takeaway ------------------------------------------------------
    is_real = bool(a.data2026)
    kind = "actual 2026 results" if is_real else "2026 model"
    delta = an26.candidate_percentile - an25.candidate_percentile
    print("\n" + "-" * 74)
    print("TAKEAWAY")
    print(f"  A weaker + larger 2026 cohort lifts the same {idx:.0f}-pt score from the "
          f"{_fmt_pct(an25.candidate_percentile)} percentile (2025 pool)")
    print(f"  to ~{_fmt_pct(an26.candidate_percentile)} ({kind}): "
          f"{delta:+.1f} pts of percentile.")
    print("  MODEL: third slot = "
          f"{'max(matematyka, fizyka)' if max_third else a.third}, third-subject "
          f"reference = {'med-pool (bio+chem co-takers)' if medpool else 'raw national'}, "
          f"{cop}.")
    print("  CAVEAT: chemia & biologia are still ranked vs ALL national extended-level "
          "takers (the")
    print("  third subject is med-pool-corrected). chem/bio-R are already med-heavy, so "
          "the residual")
    print("  flattery is smaller than the raw-national third subject was — but non-zero.")
    if is_real:
        print(f"  Using OFFICIAL 2026 stanine data ({a.data2026}); no cohort model applied.")
    else:
        print("  The 2026 figure is a MODEL (2025 shape shifted by announced means); tune "
              "means/corr/pool to stress it.")
    print("-" * 74)
    return an25, an26


if __name__ == "__main__":
    main()
