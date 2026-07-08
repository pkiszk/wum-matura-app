"""Interactive WUM matura percentile estimator.  Run:
    streamlit run src/matura/app_matura.py

Everything is an editable input: candidate scores, the third subject (math or physics),
the subject correlations (the key modelling assumption), the announced 2026 means, cohort
growth, and the applicant-pool size. Official 2025 CKE numbers are the defaults and are
shown with their source. Load real 2026 JSON to bypass the shift model entirely.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np, pandas as pd, streamlit as st

from cke_data import load_2025, load_year, SubjectStats, YearData, STANINE_BANDS
from model import Marginal, simulate_index
from wum import Candidate, analyse_year, build_2026, project_cutoff

st.set_page_config(page_title="WUM matura percentile", layout="wide")
st.title("WUM recruitment percentile — from CKE 2025 data")
st.caption("Standalone module (unrelated to the DCF/screening pipeline). Estimates where a "
           "candidate's extended-level index (chemia + biologia + matematyka/fizyka, "
           "1% = 1 pt, max 300) ranks — in 2025, and in a modelled larger/weaker 2026.")

d2025 = load_2025()

# ---------------- sidebar: all inputs -------------------------------------
with st.sidebar:
    st.header("Candidate (matura 2026)")
    chem = st.number_input("Chemia R (%)", 0, 100, 85)
    bio = st.number_input("Biologia R (%)", 0, 100, 88)
    third = st.selectbox("Third subject", ["matematyka", "fizyka"], index=0)
    third_val = st.number_input(f"{third.capitalize()} R (%)", 0, 100, 72)
    idx = chem + bio + third_val
    st.metric("Recruitment index", f"{idx} / 300")

    st.header("2026 cohort model")
    st.caption("No 2026 distribution is published yet; we shift the 2025 shape by the "
               "announced mean change. Overwrite with real data below when available.")
    bio26 = st.number_input("Biologia 2026 mean (%)", 0, 100, 41,
                            help="2025 was 46%")
    chem26 = st.number_input("Chemia 2026 mean (%)", 0, 100, 41,
                             help="2025 was 43% (CKE); brief quoted 42%")
    third_mean25 = int(d2025.get(third).mean)
    third26 = st.number_input(f"{third.capitalize()} 2026 mean (%)", 0, 100, third_mean25,
                              help=f"2025 was {third_mean25}%. Default = no change "
                                   f"(shift 0); lower it to model a weaker year.")

    st.subheader("Applicant pool (binding = chemia cohort)")
    st.caption("The WUM triple requires chemia+biologia+math/phys, so the pool is capped by "
               "the smallest cohort — chemia. Pool scales rival COUNTS, not the percentile.")
    pool25 = st.number_input("Chemia cohort 2025 (pool)", 1000, 400000, 21200,
                             help="CKE this-year grads = 20,340; broader takers ≈ 21,200.")
    pool26 = st.number_input("Chemia cohort 2026 (pool)", 1000, 400000, 33000,
                             help="Real 2026 chemia-R cohort ≈ 33,000 (+56% vs 2025).")
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

    st.header("Real 2026 data (optional)")
    up = st.file_uploader("2026 JSON (overrides the shift model)", type="json")

subjects = ["chemia", "biologia", third]
cand = Candidate(scores={"chemia": chem, "biologia": bio, third: third_val}, year=2026)
# 3x3 correlation in subject order [chemia, biologia, third]
corr = np.array([
    [1.0,  r_bc, r_c3],
    [r_bc, 1.0,  r_b3],
    [r_c3, r_b3, 1.0]])

# ---------------- run both years ------------------------------------------
an25 = analyse_year(d2025, cand, third=third, corr=corr, pool=pool25, n=n_sim)

if up is not None:
    tmp = pathlib.Path(st.session_state.get("_tmp", "/tmp/_wum2026.json"))
    tmp.write_bytes(up.getvalue())
    d2026 = load_year(tmp)
    an26 = analyse_year(d2026, cand, third=third, corr=corr, n=n_sim)
    model_label = "real uploaded 2026 data"
else:
    shifts, _ = build_2026(
        d2025, means_2026={"biologia": bio26, "chemia": chem26, third: third26},
        growth=growth)
    an26 = analyse_year(d2025, cand, third=third, corr=corr, shifts=shifts, pool=pool26, n=n_sim)
    model_label = (f"model: bio {d2025.get('biologia').mean:.0f}→{bio26} ({shifts['biologia']:+.0f}), "
                   f"chem {d2025.get('chemia').mean:.0f}→{chem26} ({shifts['chemia']:+.0f}), "
                   f"{third} {third_mean25}→{third26} ({shifts[third]:+.0f}), pool +{growth:.0%}")

# ---------------- headline ------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Percentile — 2025 pool", f"{an25.candidate_percentile:.1f}%",
          help="Share of the 2025 population scoring at or below this index")
c2.metric("Percentile — 2026 model", f"{an26.candidate_percentile:.1f}%",
          f"{an26.candidate_percentile - an25.candidate_percentile:+.1f} pts")
c3.metric("Est. rivals above (2026)", f"{an26.rank_above:,.0f}",
          help=f"in a pool of {an26.pool:,.0f}")

_dir = ("rises" if an26.rank_above > an25.rank_above else
        "falls" if an26.rank_above < an25.rank_above else "is flat")
st.info(
    f"**{model_label}.** Two forces pull opposite ways on the same **{idx}-pt** score: the "
    f"*weaker* 2026 field lifts its **percentile** "
    f"({an25.candidate_percentile:.1f}% → {an26.candidate_percentile:.1f}%), while the "
    f"*larger* pool (+{growth:.0%}) raises the **absolute rivals above** — net, the rival "
    f"count **{_dir}** ({an25.rank_above:,.0f} → {an26.rank_above:,.0f}). "
    f"Percentile = *how exceptional*; rival count = *how many are ahead*.")

# ---------------- cut-off (próg) projection -------------------------------
if cut2025 > 0:
    proj = project_cutoff(an25, an26, cut_base=cut2025,
                          pool_base=pool25, pool_target=pool26, seats_growth=seats_growth)
    st.subheader("Projected 2026 admission cut-off (próg)")
    k1, k2, k3 = st.columns(3)
    k1.metric("2025 cut-off", f"{proj['cut_base']:.0f}")
    k2.metric("Projected 2026 cut-off", f"{proj['cut_target']:.0f}", f"{proj['net']:+.0f}")
    k3.metric("Candidate margin (2026)", f"{idx - proj['cut_target']:+.0f}",
              help=f"vs 245 index; 2025 margin was {idx - proj['cut_base']:+.0f}")
    st.caption(
        f"Held at ~**{proj['seats']:,.0f}** seats (2025 admit rate {proj['admit_base']*100:.1f}% → "
        f"2026 {proj['admit_target']*100:.1f}% as the pool grows). Two opposing forces: pool "
        f"growth pushes the cut **{proj['pool_effect']:+.0f}**, the weaker field pulls it "
        f"**{proj['weakening_effect']:+.0f}** → net **{proj['net']:+.0f}**. "
        f"Candidate 245 clears it by **{idx - proj['cut_target']:+.0f}**.")

# ---------------- per-subject table ---------------------------------------
st.subheader("Candidate per-subject standing (vs all 2025 extended-level takers)")
rows = []
for s in subjects:
    stt = d2025.get(s)
    rows.append({"subject": s, "candidate %": cand.scores[s],
                 "percentile 2025": round(an25.candidate_subject_pct[s], 1),
                 "subj mean %": stt.mean, "subj median %": stt.median,
                 "subj sd %": stt.sd, "N (R)": stt.n, "source": stt.source.split(";")[0]})
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ---------------- index distribution chart --------------------------------
st.subheader("Index distribution: 2025 vs 2026 model")
bins = np.arange(0, 301, 5)
h25, _ = np.histogram(an25.joint.index_samples, bins=bins, density=True)
h26, _ = np.histogram(an26.joint.index_samples, bins=bins, density=True)
centers = (bins[:-1] + bins[1:]) / 2
chart_df = pd.DataFrame({"2025": h25, "2026 model": h26}, index=centers)
st.line_chart(chart_df)
st.caption(f"Candidate index = {idx}. 2025 pool mean "
           f"{an25.joint.index_samples.mean():.0f}; 2026 model mean "
           f"{an26.joint.index_samples.mean():.0f} (max 300).")

# ---------------- stanine reference ---------------------------------------
with st.expander("Official 2025 stanine tables (the percentile boundaries we build on)"):
    st.caption("CKE 'skala staninowa' 2025: each stanine holds a fixed population fraction "
               f"{tuple(int(b*100) for b in STANINE_BANDS)}%. These ARE the published "
               "percentile boundaries; the module interpolates the score→percentile curve "
               "from them.")
    for s in ["chemia", "biologia", "matematyka", "fizyka"]:
        stt = d2025.get(s)
        st.write(f"**{s}** (N={stt.n:,}, mean {stt.mean}%, sd {stt.sd}%) — "
                 f"stanine upper bounds: {stt.stanine_upper}")

st.caption("⚠️ Reference pool = ALL national extended-level takers, not the self-selected "
           "WUM applicant field (stronger) — true med-competition standing is somewhat lower. "
           "The 2026 figure is a model; stress it via the correlation, mean, and pool inputs.")
