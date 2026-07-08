"""Interactive WUM matura percentile estimator.  Run:
    streamlit run src/matura/app_matura.py

2026 basis is a toggle:
  * "Official 2026 CKE results" (default when the bundled/uploaded data is present) —
    the real published stanine curves; no cohort model applied.
  * "What-if model" — the 2025 shape shifted by assumed 2026 means, for scenarios.
Everything else is editable: candidate scores, third subject (math/physics), subject
correlations, pool sizes, and the admission cut-off. Official 2025 CKE numbers are the
defaults, shown with their source.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np, pandas as pd, streamlit as st

from cke_data import load_2025, load_year, STANINE_BANDS, THIRD_MEDPOOL_GAP
from wum import Candidate, analyse_year, build_2026, project_cutoff, wum_corr


def _find_bundled_2026():
    """Locate a bundled 2026.json — next to this file (deploy repo) or in AICF/data/matura."""
    here = pathlib.Path(__file__).resolve().parent
    for p in (here / "2026.json", here.parents[1] / "data" / "matura" / "2026.json"):
        if p.exists():
            return p
    return None


st.set_page_config(page_title="WUM matura percentile", layout="wide")
st.title("WUM recruitment percentile — CKE 2025 & 2026 data")
st.caption("Estimates where a candidate's WUM recruitment index (chemia + biologia + "
           "matematyka/fizyka, extended level, 1% = 1 pt, max 300) ranks among Polish "
           "maturzyści — from official CKE data for 2025 and 2026 (with a what-if model option).")
_REPO = "https://github.com/pkiszk/wum-matura-app"
st.markdown(
    f"📖 **[Full methodology & sources]({_REPO}/blob/main/METHODOLOGY.md)** · "
    f"[README]({_REPO}/blob/main/README.md) · [source code]({_REPO}) — "
    "every number here is reproducible and sourced (see also the expander at the bottom).")

d2025 = load_2025()
bundled_2026 = _find_bundled_2026()

# ---------------- sidebar: all inputs -------------------------------------
with st.sidebar:
    st.header("Candidate (matura 2026)")
    chem = st.number_input("Chemia R (%)", 0, 100, 85)
    bio = st.number_input("Biologia R (%)", 0, 100, 88)
    third = st.selectbox("Third subject", ["matematyka", "fizyka"], index=0)
    third_val = st.number_input(f"{third.capitalize()} R (%)", 0, 100, 72)
    idx = chem + bio + third_val
    st.metric("Recruitment index", f"{idx} / 300")

    st.header("2026 basis")
    up = st.file_uploader("Upload custom 2026 JSON (optional)", type="json")
    choices = (["Official 2026 CKE results"] if bundled_2026 else []) + \
              ["What-if model (2025 shifted)"]
    src = st.radio("Use for 2026", choices, index=0,
                   help="Official = real published 2026 stanine curves. "
                        "Model = shift the 2025 shape by assumed means (scenarios).")
    use_real = (up is not None) or (src == "Official 2026 CKE results")

    d2026 = None
    real_src_note = ""
    if up is not None:
        tmp = pathlib.Path("/tmp/_wum2026_upload.json")
        tmp.write_bytes(up.getvalue())
        d2026 = load_year(tmp)
        use_real = True
        real_src_note = "uploaded 2026 JSON"
    elif use_real and bundled_2026 is not None:
        d2026 = load_year(bundled_2026)
        real_src_note = "official CKE 2026 centyle curves (published 2026-07-08)"

    # model-only inputs (hidden when using real data)
    bio26 = chem26 = third26 = None
    third_mean25 = int(d2025.get(third).mean)
    if not use_real:
        st.caption("Shift the 2025 shape by the assumed 2026 means (no real data used).")
        bio26 = st.number_input("Biologia 2026 mean (%)", 0, 100, 41, help="2025 was 46%")
        chem26 = st.number_input("Chemia 2026 mean (%)", 0, 100, 41,
                                 help="2025 was 43% (CKE); brief quoted 42%")
        third26 = st.number_input(f"{third.capitalize()} 2026 mean (%)", 0, 100, third_mean25,
                                  help=f"2025 was {third_mean25}%. Default = no change (shift 0).")
    elif d2026 is not None:
        st.success(f"Using {real_src_note}. No cohort model applied.")

    st.subheader("Applicant pool (binding = chemia cohort)")
    st.caption("The WUM triple requires chemia+biologia+math/phys, so the pool is capped by "
               "the smallest cohort — chemia. Pool scales rival COUNTS, not the percentile.")
    pool25 = st.number_input("Chemia cohort 2025 (pool)", 1000, 400000, int(d2025.get("chemia").n),
                             help="Official CKE 2025 grads = 20,340 — same basis as the 2026 "
                                  "grads count, so growth reads a clean +56%.")
    default_pool26 = int(d2026.get("chemia").n) if d2026 is not None else 31691
    pool26 = st.number_input("Chemia cohort 2026 (pool)", 1000, 400000, default_pool26,
                             help="Auto-filled from official 2026 data (31,691 grads) when that "
                                  "basis is on; editable for scenarios.")
    growth = pool26 / pool25 - 1.0
    st.caption(f"Implied pool growth: **{growth:+.0%}**  (overall matura cohort ≈ +30%; "
               f"the med-binding chemia pool grew faster).")

    st.subheader("Admission cut-off (próg)")
    cut2025 = st.number_input("2025 cut-off for this programme", 0, 300, 221,
                              help="Last-admitted index in 2025. 0 = skip the projection.")
    seats_growth = st.slider("2026 seats change", -0.20, 0.50, 0.0, 0.05,
                             help="WUM rarely expands limits; stress it here.")

    st.header("Modelling assumptions")
    r_bc = st.slider("corr biologia–chemia", 0.0, 0.95, 0.60, 0.05)
    r_b3 = st.slider(f"corr biologia–{third}", 0.0, 0.95, 0.45, 0.05)
    r_c3 = st.slider(f"corr chemia–{third}", 0.0, 0.95, 0.50, 0.05)

    st.subheader("Copula tail dependence")
    st.caption("The admission cut-off lives in the top ~3%. A Gaussian copula has ZERO "
               "upper-tail dependence, so it decouples exactly there; a Student-t copula "
               "couples joint extremes. Lower ν = heavier joint tails.")
    gaussian = st.checkbox("Gaussian copula (ν → ∞)", value=False,
                           help="Old behaviour: zero upper-tail dependence.")
    nu_val = st.slider("Student-t ν (df)", 3, 40, 6, 1, disabled=gaussian,
                       help="5–8 is a reasonable default for co-moving exam scores.")
    nu = None if gaussian else float(nu_val)

    st.subheader("Third subject: rule & reference pool")
    max_third = st.checkbox("Third slot = max(matematyka, fizyka)", value=True,
                            help="WUM takes the BETTER of maths or physics. Modelling one "
                                 "marginal ignores that order-statistic uplift.")
    medpool = st.checkbox("Med-pool reference for the third subject", value=True,
                          help="National maths/physics R is dominated by non-med candidates; "
                               "rank the third subject against bio+chem co-takers instead.")
    st.caption("National → med-pool mean uplift (pts), interim estimate — replace with "
               "published admitted-cohort profiles when available.")
    gap_math = st.slider("matematyka med-pool gap (+pts)", 0, 25,
                         int(THIRD_MEDPOOL_GAP["matematyka"]), 1, disabled=not medpool)
    gap_phys = st.slider("fizyka med-pool gap (+pts)", 0, 25,
                         int(THIRD_MEDPOOL_GAP["fizyka"]), 1, disabled=not medpool)
    medpool_gap = {"matematyka": float(gap_math), "fizyka": float(gap_phys)}

    n_sim = st.select_slider("Monte-Carlo samples", [50_000, 100_000, 200_000, 500_000],
                             value=200_000)

subjects = ["chemia", "biologia", third]
cand = Candidate(scores={"chemia": chem, "biologia": bio, third: third_val}, year=2026)
# Correlation matrix. max_third needs a 4x4 over [chemia, biologia, matematyka, fizyka];
# otherwise a 3x3 over [chemia, biologia, third].
if max_third:
    corr = wum_corr(r_bc, r_b3, r_c3)
else:
    corr = np.array([
        [1.0,  r_bc, r_c3],
        [r_bc, 1.0,  r_b3],
        [r_c3, r_b3, 1.0]])

_kw = dict(third=third, corr=corr, n=n_sim, nu=nu, medpool=medpool,
           max_third=max_third, medpool_gap=medpool_gap)

# ---------------- run both years ------------------------------------------
an25 = analyse_year(d2025, cand, pool=pool25, **_kw)

if use_real and d2026 is not None:
    an26 = analyse_year(d2026, cand, pool=pool26, **_kw)
    year_label = "2026 (actual)"
    source_note = f"**Official 2026 CKE results** ({real_src_note})"
else:
    shifts, _ = build_2026(
        d2025, means_2026={"biologia": bio26, "chemia": chem26, third: third26}, growth=growth)
    an26 = analyse_year(d2025, cand, shifts=shifts, pool=pool26, **_kw)
    year_label = "2026 model"
    source_note = (f"**What-if model** (bio {d2025.get('biologia').mean:.0f}→{bio26} "
                   f"{shifts['biologia']:+.0f}, chem {d2025.get('chemia').mean:.0f}→{chem26} "
                   f"{shifts['chemia']:+.0f}, {third} {third_mean25}→{third26} {shifts[third]:+.0f})")

# ---------------- model banner --------------------------------------------
_cop = "Gaussian copula (ν→∞)" if nu is None else f"Student-t copula (ν={nu:g})"
_third_rule = "max(matematyka, fizyka)" if max_third else third
st.caption(f"⚙️ Model: **{_cop}** · third slot **{_third_rule}** · third-subject reference "
           f"**{'med-pool' if medpool else 'raw national'}**.")

# ---------------- headline ------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Percentile — 2025 pool", f"{an25.candidate_percentile:.1f}%",
          help="Share of the 2025 population scoring at or below this index")
c2.metric(f"Percentile — {year_label}", f"{an26.candidate_percentile:.1f}%",
          f"{an26.candidate_percentile - an25.candidate_percentile:+.1f} pts")
c3.metric(f"Est. rivals above ({year_label})", f"{an26.rank_above:,.0f}",
          help=f"in a pool of {an26.pool:,.0f}")

_dir = ("rises" if an26.rank_above > an25.rank_above else
        "falls" if an26.rank_above < an25.rank_above else "is flat")
st.info(
    f"{source_note}. Two forces pull opposite ways on the same **{idx}-pt** score: the "
    f"*weaker* 2026 field lifts its **percentile** "
    f"({an25.candidate_percentile:.1f}% → {an26.candidate_percentile:.1f}%), while the "
    f"*larger* pool (+{growth:.0%}) raises the **absolute rivals above** — net, the rival "
    f"count **{_dir}** ({an25.rank_above:,.0f} → {an26.rank_above:,.0f}). "
    f"Percentile = *how exceptional*; rival count = *how many are ahead*.")

# ---------------- cut-off (próg) projection -------------------------------
if cut2025 > 0:
    proj = project_cutoff(an25, an26, cut_base=cut2025,
                          pool_base=an25.pool, pool_target=an26.pool, seats_growth=seats_growth)
    st.subheader("2026 admission cut-off (próg) — estimated")
    k1, k2, k3 = st.columns(3)
    k1.metric("2025 cut-off", f"{proj['cut_base']:.0f}")
    k2.metric("2026 est. cut-off", f"{proj['cut_target']:.0f}", f"{proj['net']:+.0f}",
              help="A PROJECTION from seats & pool growth — not a published figure. WUM's "
                   "real 2026 próg is set at recruitment, after applications close.")
    k3.metric("Candidate margin", f"{idx - proj['cut_target']:+.0f}",
              help=f"vs 245 index; 2025 margin was {idx - proj['cut_base']:+.0f}")
    st.caption(
        f"**Estimated, not actual** — projected by holding seats ~fixed while the pool grows; "
        f"WUM publishes the real próg only at recruitment. "
        f"Held at ~**{proj['seats']:,.0f}** seats (2025 admit rate {proj['admit_base']*100:.1f}% → "
        f"2026 {proj['admit_target']*100:.1f}% as the pool grows). Two opposing forces: pool "
        f"growth pushes the cut **{proj['pool_effect']:+.0f}**, the weaker field pulls it "
        f"**{proj['weakening_effect']:+.0f}** → net **{proj['net']:+.0f}**. "
        f"Candidate {idx} clears it by **{idx - proj['cut_target']:+.0f}**.")

# ---------------- per-subject table ---------------------------------------
st.subheader("Candidate per-subject standing")
rows = []
for s in subjects:
    st25 = d2025.get(s)
    ref = "med-pool" if (medpool and s == third) else "national"
    row = {"subject": s, "ref pool": ref, "candidate %": cand.scores[s],
           "%ile 2025": round(an25.candidate_subject_pct[s], 1),
           f"%ile {year_label}": round(an26.candidate_subject_pct[s], 1),
           "2025 mean %": st25.mean}
    if d2026 is not None:
        st26 = d2026.get(s)
        row["2026 mean %"] = st26.mean
        row["Δ mean"] = round(st26.mean - st25.mean, 1)
    row["2025 N (R)"] = st25.n
    if d2026 is not None:
        row["2026 N (R)"] = d2026.get(s).n
    rows.append(row)
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
if medpool:
    st.caption(
        f"**Third subject ({third}) is ranked against the MED POOL**, not all national "
        f"takers. National {third} R is dominated by non-med candidates (engineering, "
        f"econ, CS), so the raw national percentile overstates a med applicant. Med-pool "
        f"= national marginal reweighted by +{medpool_gap[third]:.0f} pts of mean. "
        f"For {third} {third_val}%: national %ile would read "
        f"**{an25.extras['third_national_pct']:.1f}%** (2025) / "
        f"**{an26.extras['third_national_pct']:.1f}%** ({year_label}) — the med-pool "
        f"figures above are materially lower.")
if d2026 is not None:
    st.caption("Means & N are official CKE 2026 figures (Wstępne informacje EM26, Tabela 2 — "
               "all this-year graduates). Biggest moves: **fizyka −10** (52→42) and "
               "**matematyka +4** (33→37); biologia −5, chemia −2. The percentile/cut-off "
               "read the published **centyle curve** directly, so the mean column is context, "
               "not an input.")

# ---------------- index distribution chart --------------------------------
st.subheader(f"Index distribution: 2025 vs {year_label}")
bins = np.arange(0, 301, 5)
h25, _ = np.histogram(an25.joint.index_samples, bins=bins, density=True)
h26, _ = np.histogram(an26.joint.index_samples, bins=bins, density=True)
centers = (bins[:-1] + bins[1:]) / 2
chart_df = pd.DataFrame({"2025": h25, year_label: h26}, index=centers)
st.line_chart(chart_df)
st.caption(f"Candidate index = {idx}. 2025 pool mean "
           f"{an25.joint.index_samples.mean():.0f}; {year_label} mean "
           f"{an26.joint.index_samples.mean():.0f} (max 300).")

# ---------------- full methodology (rendered inline) ----------------------
_doc = pathlib.Path(__file__).resolve().parent / "METHODOLOGY.md"
with st.expander("📖 Full methodology — sources, formulas, assumptions (read in-app)"):
    if _doc.exists():
        st.caption(f"Rendered from METHODOLOGY.md in the repo · "
                   f"[open on GitHub]({_REPO}/blob/main/METHODOLOGY.md)")
        st.markdown(_doc.read_text(encoding="utf-8"))
    else:
        st.markdown(f"See the full methodology on "
                    f"[GitHub]({_REPO}/blob/main/METHODOLOGY.md).")

# ---------------- centyle / stanine reference -----------------------------
with st.expander("Official CKE percentile data (the curves we build on)"):
    st.caption("The engine reads each subject's **centyle curve** (skala centylowa) — the "
               "published score→percentile mapping at ~1-pt resolution — directly, with no "
               "normal-curve assumption. The 9-band **stanine** table (fractions "
               f"{tuple(int(b*100) for b in STANINE_BANDS)}%) is the coarser fallback shown "
               "below for reference.")
    for s in ["chemia", "biologia", "matematyka", "fizyka"]:
        st25 = d2025.get(s)
        cent = "centyle ✓" if st25.centile else "stanine only"
        line = (f"**{s}** — 2025 (N={st25.n:,}, mean {st25.mean}%, {cent}): "
                f"stanine upper bounds {st25.stanine_upper}")
        if d2026 is not None and s in d2026.subjects:
            line += f"  ·  2026 (N={d2026.get(s).n:,}): stanine {d2026.get(s).stanine_upper}"
        st.write(line)

foot = ("Using OFFICIAL 2026 centyle curves (fine published percentile data)."
        if (use_real and d2026 is not None) else
        "2026 here is a what-if model; switch the basis above to official data.")
st.caption(f"ℹ️ {foot}  ⚠️ The third subject is med-pool-corrected, but **chemia & biologia "
           "are still ranked vs ALL national extended-level takers**. chem/bio-R are already "
           "med-heavy so the residual flattery is smaller than the raw-national third subject "
           "was — but non-zero; true med-competition standing is somewhat lower still. "
           "Year-over-year *change* is the robust part.")
