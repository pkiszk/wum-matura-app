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

from cke_data import load_2025, load_year, STANINE_BANDS
from wum import Candidate, analyse_year, build_2026, project_cutoff


def _find_bundled_2026():
    """Locate a bundled 2026.json — next to this file (deploy repo) or in AICF/data/matura."""
    here = pathlib.Path(__file__).resolve().parent
    for p in (here / "2026.json", here.parents[1] / "data" / "matura" / "2026.json"):
        if p.exists():
            return p
    return None


st.set_page_config(page_title="WUM matura percentile", layout="wide")
st.title("WUM recruitment percentile — CKE 2025 & 2026 data")
st.caption("Standalone module (unrelated to the DCF/screening pipeline). Estimates where a "
           "candidate's extended-level index (chemia + biologia + matematyka/fizyka, "
           "1% = 1 pt, max 300) ranks — in 2025, and in 2026 (official results, with a "
           "what-if model option).")

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
        real_src_note = "official CKE 2026 stanines (published 2026-07-08)"

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
    n_sim = st.select_slider("Monte-Carlo samples", [50_000, 100_000, 200_000, 500_000],
                             value=200_000)

subjects = ["chemia", "biologia", third]
cand = Candidate(scores={"chemia": chem, "biologia": bio, third: third_val}, year=2026)
# 3x3 correlation in subject order [chemia, biologia, third]
corr = np.array([
    [1.0,  r_bc, r_c3],
    [r_bc, 1.0,  r_b3],
    [r_c3, r_b3, 1.0]])

# ---------------- run both years ------------------------------------------
an25 = analyse_year(d2025, cand, third=third, corr=corr, pool=pool25, n=n_sim)

if use_real and d2026 is not None:
    an26 = analyse_year(d2026, cand, third=third, corr=corr, pool=pool26, n=n_sim)
    year_label = "2026 (actual)"
    source_note = f"**Official 2026 CKE results** ({real_src_note})"
else:
    shifts, _ = build_2026(
        d2025, means_2026={"biologia": bio26, "chemia": chem26, third: third26}, growth=growth)
    an26 = analyse_year(d2025, cand, third=third, corr=corr, shifts=shifts, pool=pool26, n=n_sim)
    year_label = "2026 model"
    source_note = (f"**What-if model** (bio {d2025.get('biologia').mean:.0f}→{bio26} "
                   f"{shifts['biologia']:+.0f}, chem {d2025.get('chemia').mean:.0f}→{chem26} "
                   f"{shifts['chemia']:+.0f}, {third} {third_mean25}→{third26} {shifts[third]:+.0f})")

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
    st.subheader(f"2026 admission cut-off (próg) — {year_label}")
    k1, k2, k3 = st.columns(3)
    k1.metric("2025 cut-off", f"{proj['cut_base']:.0f}")
    k2.metric(f"{year_label} cut-off", f"{proj['cut_target']:.0f}", f"{proj['net']:+.0f}")
    k3.metric("Candidate margin", f"{idx - proj['cut_target']:+.0f}",
              help=f"vs 245 index; 2025 margin was {idx - proj['cut_base']:+.0f}")
    st.caption(
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
    row = {"subject": s, "candidate %": cand.scores[s],
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
if d2026 is not None:
    st.caption("Means & N are official CKE 2026 figures (Wstępne informacje EM26, Tabela 2 — "
               "all this-year graduates). Biggest moves: **fizyka −10** (52→42) and "
               "**matematyka +4** (33→37); biologia −5, chemia −2. The percentile/cut-off "
               "read the stanine curve directly, so the mean column is context, not an input.")

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

# ---------------- stanine reference ---------------------------------------
with st.expander("Official CKE stanine tables (the percentile boundaries we build on)"):
    st.caption("Each stanine holds a fixed population fraction "
               f"{tuple(int(b*100) for b in STANINE_BANDS)}%. These ARE the published "
               "percentile boundaries; the module interpolates the score→percentile curve "
               "from them — no normal-curve assumption.")
    for s in ["chemia", "biologia", "matematyka", "fizyka"]:
        st25 = d2025.get(s)
        line = (f"**{s}** — 2025 (N={st25.n:,}, mean {st25.mean}%): "
                f"upper bounds {st25.stanine_upper}")
        if d2026 is not None and s in d2026.subjects:
            line += f"  ·  2026 (N={d2026.get(s).n:,}): upper bounds {d2026.get(s).stanine_upper}"
        st.write(line)

foot = ("Using OFFICIAL 2026 stanine curves — the blind forecast (shift-model) was confirmed "
        "by these actuals." if (use_real and d2026 is not None) else
        "2026 here is a what-if model; switch the basis above to official data.")
st.caption(f"ℹ️ {foot}  ⚠️ Reference pool = ALL national extended-level takers, not the "
           "self-selected WUM applicant field (stronger) — true med-competition standing is "
           "somewhat lower. Year-over-year *change* is the robust part.")
