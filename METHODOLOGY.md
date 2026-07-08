# Methodology — WUM matura percentile & cut-off module

A complete, verifiable account of how this module turns published CKE 2025 data into
(a) a candidate's percentile, (b) a modelled 2026 percentile, and (c) a projected 2026
admission cut-off. Every number below is reproducible from the commands in §10, and every
input is traceable to an official source in §1. Nothing here is a black box.

Scope note: this module is standalone and unrelated to the rest of the AICF (DCF/investing)
project. It shares only `numpy`.

---

## 0. The object we are ranking

WUM (Warszawski Uniwersytet Medyczny) ranks candidates on a **recruitment index**:

    index = chemia_R + biologia_R + (matematyka_R  OR  fizyka_R)

each subject a matura **extended-level** ("poziom rozszerzony") result in **%**, with the
rule **1% = 1 point**, so `index ∈ [0, 300]`. Physics may substitute for mathematics.
The worked candidate: chemia 85, biologia 88, matematyka 72 → **index = 245**.

Two questions the module answers:
1. **Percentile** — what share of candidates score at or below 245? (how exceptional)
2. **Cut-off (próg)** — given last year's threshold, what will this year's be? (admit or not)

---

## 1. Data sources (provenance)

All figures are official CKE (Centralna Komisja Egzaminacyjna) / OKE, whole-percent
precision (that is what CKE publishes — no decimals).

### 1a. Distribution parameters, 2025 extended level
National subject reports ("raport krajowy"), hosted on oke.poznan.pl
(`em2023_<subject>_raport_kraj_2025.pdf`):

| Subject (R) | N (zdających) | mean | median | SD | modal |
|---|---:|---:|---:|---:|---:|
| matematyka | 67 384 | 33% | 28% | 26% | 0% |
| biologia   | 41 718 | 46% | 45% | 24% | 20% |
| chemia     | 20 340 | 43% | 40% | 26% | 8% |
| fizyka     | 13 961 | 52% | 53% | 29% | 13% |

> **Verify:** open each PDF, find the parameter table ("Ogółem / Formuła 2023"). These
> live in code at `cke_data.py` → `DATA_2025`. Note: mean/median/SD are **displayed only**;
> they are **not** used in the percentile math (see §2 — we use the stanine curve instead).
> The SD is never used at all; the mean is used only to size the 2026 shift (§5).

### 1b. Stanine tables — the primary object
CKE "Skale staninowe wyników — egzamin maturalny 2025". A stanine ("stanina") is a
9-class scale where each class holds a **fixed fraction of the population**:

    band fractions = [4, 7, 12, 17, 20, 17, 12, 7, 4] %   (sum = 100%)

CKE publishes, per subject, the **score range** covered by each of the 9 classes. Because
the fractions are fixed, the **upper score of each class is a published percentile
boundary**. We store the 9 upper bounds per subject (`cke_data.py` → `stanine_upper`):

| Subject (R) | stanine upper bounds (score %, classes 1→9) |
|---|---|
| matematyka | 0, 2, 8, 22, 38, 56, 76, 100, 100 |
| biologia   | 10, 15, 23, 35, 53, 67, 77, 85, 100 |
| chemia     | 5, 8, 17, 32, 48, 65, 80, 90, 100 |
| fizyka     | 7, 12, 22, 42, 63, 80, 90, 97, 100 |

(For matematyka, CKE printed classes 8 & 9 as one range 78–100%; we encode both at 100,
so the 0.89→1.00 step is a single segment — mathematically identical.)

The **cumulative** fraction at each upper bound is the running sum of the bands:

    cum = [0.04, 0.11, 0.23, 0.40, 0.60, 0.77, 0.89, 0.96, 1.00]

### 1c. Cohort sizes (for pool & cut-off)
User-supplied official 2026 figures (extended-level counts):

| Subject (R) | 2025 | 2026 | change |
|---|---:|---:|---:|
| matematyka | 71 000 | 93 000 | +31% |
| biologia   | 44 400 | 71 000 | +60% |
| chemia     | 21 200 | 33 000 | **+56%** |

Overall matura cohort grew ~+30%; the med-binding **chemia** cohort grew **+56%** (see §6).
(These broad counts differ slightly from §1a's "this-year graduates" N — e.g. chemia
21 200 vs 20 340 — because they include repeat/adult takers. For pool sizing the broader
count is the right basis; for distribution shape we use §1a/§1b.)

---

## 2. Per-subject marginal: score → percentile (the empirical CDF)

We build each subject's cumulative distribution function (CDF) by **linear interpolation
between the stanine knots**, anchored at (0, 0):

    knots_x = [0] + stanine_upper           # scores
    knots_y = [0] + cum                     # cumulative fractions
    percentile(score) = 100 · interp(score; knots_x → knots_y)

This respects each subject's real **skew** (e.g. matematyka R: modal 0%, mean 33% — heavily
right-skewed) rather than assuming a symmetric bell curve. Code: `model.py` → `Marginal`.

### Worked example — chemia 85 (hand-checkable)
chemia knots: (0,0) (5,.04) (8,.11) (17,.23) (32,.40) (48,.60) (65,.77) (80,.89) (90,.96) (100,1).
85 lies between (80, 0.89) and (90, 0.96):

    percentile(85) = 0.89 + (85−80)/(90−80) · (0.96−0.89) = 0.89 + 0.5·0.07 = 0.925 → 92.5%

Same method gives **biologia 88 → 96.8%**, **matematyka 72 → 86.6%**. All three are
reproduced by `test_matura.py` and printed by `report.py`.

### Sampling (inverse CDF)
To simulate a candidate we invert the curve: draw `u ~ Uniform(0,1)`, then
`score = interp(u; knots_y → knots_x)`. Code: `Marginal.quantile`.

---

## 3. Joint distribution of the index (Gaussian copula)

The index is a **sum of three subjects**, so its distribution depends on how the subjects
**co-move** — a joint distribution CKE does **not** publish. We therefore combine the three
empirical marginals with a **Gaussian copula**: the marginals stay exactly as in §2 (skew
preserved), and only the *dependence* is modelled as multivariate-normal.

Procedure (`model.py` → `simulate_index`), subject order `[chemia, biologia, third]`:

1. Correlation matrix `R` (3×3). Defaults (`default_corr`, tunable):
   `bio–chem = 0.60`, `chem–third = 0.50`, `bio–third = 0.45` (math); physics analogues higher.
2. Cholesky factor `L` with `R = L·Lᵀ` (nudged onto the PSD cone if a hand-entered `R`
   is not positive-definite).
3. Draw `Z ~ N(0, I)` of shape `(N, 3)`; correlate: `X = Z · Lᵀ`.
4. Map to uniforms with the standard normal CDF: `U = Φ(X)` (Φ via `math.erf`, no scipy).
5. Invert each marginal: `score_j = Q_j(U_j)`; `index = Σ_j score_j`.

`N = 200 000` samples, fixed `seed = 12345` (reproducible; `test_matura.py` checks that same
seed → identical output).

**Why a copula, and what the assumption costs:** higher correlation fattens the tails of the
sum (high scorers cluster), which moves extreme percentiles. Correlation is the single
biggest modelling assumption; it is a slider in the app and an argument in code precisely so
you can stress it. The marginals themselves carry **no** normality assumption.

---

## 4. Candidate percentile & rival count

Given `N` simulated indices and the candidate index `v = 245`:

    percentile(v) = 100 · mean( index_samples ≤ v )
    rivals_above  = mean( index_samples > v ) · pool

`pool` = the relevant applicant population (see §6). Code: `JointResult.percentile_of`,
`JointResult.rank_above`.

**2025 result:** index mean ≈ 122, median ≈ 117, SD ≈ 64, skew ≈ +0.32; **245 → 96.3%**;
rivals above ≈ 775 in a 21 200 pool.

**Sanity vs a normal approximation (why skew matters):** a naive `Φ((245−122)/64)` gives
97.2% — i.e. a bell curve would *overstate* the candidate by ~1 point, because the real
index is right-skewed (fatter high tail). Reproduce with the snippet in §10.

---

## 5. The 2026 curves

> **2026-07-08 update — real data now available.** CKE published the 2026 extended-level
> stanine tables. They are ingested in `data/matura/2026.json` (N + stanine bounds per
> subject, each with a page citation) and are the **default** basis (`--data2026` / the
> app's "Official 2026 CKE results" toggle). When real data is used, the 2026 curves are
> built by §2 exactly like 2025 — **no model**. The subsection below documents the
> *what-if model* that (a) is still available for scenarios and (b) was used to make a
> blind forecast *before* any 2026 data existed. That forecast was then confirmed by the
> actuals: predicted 245 → 97.3th percentile & cut-off ~229; **real data: 97.3% & ~228.**
> The real 2026 stanine upper bounds (extended level): matematyka N=88 856
> [0,2,8,22,42,60,74,100,100]; biologia N=67 312 [8,12,18,28,43,58,72,82,100]; chemia
> N=31 691 [3,7,15,28,47,63,77,87,100]; fizyka N=19 364 [3,7,13,28,50,68,80,90,100].
> Note the *shape* changed, not just the level (e.g. matematyka strengthened mid-range),
> which a pure mean-shift cannot capture — so real data is strictly preferred where it exists.
> Official 2026 R means (CKE *Wstępne informacje* Tabela 2, all this-year graduates):
> matematyka **37** (2025: 33, +4), biologia **41** (46, −5), chemia **41** (43, −2),
> fizyka **42** (52, −10). These are context only — the percentile/cut-off read the stanine
> curve directly, never the mean. (Deriving a mean from the coarse 9-point stanine curve
> runs ~1–2 pts low, so the module now uses these published means for display.)

### 5a. The what-if model (used when real data is absent)

We do **not** invent a 2026 shape. We take each 2025 empirical marginal and **shift it
horizontally** by the announced change in its mean, then clip to [0,100]:

    shift_subject = mean_2026 − mean_2025
    score_knots_2026 = clip( score_knots_2025 + shift_subject , 0 , 100 )

Announced means → shifts: **biologia 46→41 = −5**, **chemia 43→41 = −2**, **matematyka
unchanged = 0** (all editable). Code: `wum.build_2026` (computes shifts) + `Marginal(shift=…)`.

**Rationale:** a horizontal shift preserves the published *shape/skew* while reproducing the
announced mean drop — which is exactly the signature of a larger, weaker cohort. The copula
(§3) is re-run on the shifted marginals.

**2026 result:** **245 → 97.3%** (the weaker field thins the top, so a fixed score ranks
higher). This is the "2026 curve below 2025 on the right" you see in the app chart — both
curves are densities (area = 1), so lower-on-the-right ⇔ higher-on-the-left.

**Caveats specific to this step:**
- Clipping at 0/100 piles a little mass at the boundaries, so the *realized* mean shift is
  marginally smaller than the nominal −5/−2 (a second-order effect).
- A rigid translation changes the center, not the spread. If you believe the spread also
  changes, that is a separate lever (not currently modelled; noted as future work).
- When **real** 2026 distributions are published, bypass the whole shift model: put the
  actual stanine/parameter numbers in a JSON file and load it (`--data2026` / uploader).

---

## 6. Applicant pool (why chemia, why +56%)

The index requires chemia **and** biologia **and** (math|physics), so the number of people
who can be in the competition is capped by the **smallest** cohort — **chemia** (33 000 <
71 000 bio < 93 000 math in 2026). Nearly everyone taking chemia-R is on the med track and
also takes bio-R, so **chemia cohort ≈ med-applicant pool**. Therefore:

- `pool_2025 = 21 200`, `pool_2026 = 33 000` → **pool growth = +56%** (not the +30% overall).
- Percentile (§4) is **scale-free** — pool size does not affect it. Pool only scales
  **absolute counts** (rivals, and the cut-off headcount in §7).

Consequence: with the real +56%, rivals-above **rises** 775 → 893 even though the percentile
improves — more people, but weaker. Both facts are true; they answer different questions.

---

## 7. Cut-off (próg) projection

A cut-off is the score of the **last admitted** candidate, so
`#(applicants ≥ cut) = #seats`. We hold seats fixed (they rarely track cohort size) and read
the score at that same headcount in the 2026 distribution. Code: `wum.project_cutoff`.

    frac_base   = mean( index_base ≥ cut_base )           # 2025 in-pool admit rate
    seats       = pool_base · frac_base · (1 + seats_growth)
    admit_2026  = seats / pool_target                     # lower: same seats, bigger pool
    cut_2026    = quantile( index_target , 1 − admit_2026 )

**Decomposition** (two opposing forces):

    cut_poolonly     = quantile( index_base , 1 − admit_2026 )   # bigger pool, 2025 shape
    pool_effect      = cut_poolonly − cut_base                   # (+) more rivals, same seats
    weakening_effect = cut_2026 − cut_poolonly                   # (−) weaker field
    net              = cut_2026 − cut_base = pool_effect + weakening_effect

**Worked result** (cut_base = 221, pool 21 200→33 000, means bio −5 / chem −2, seats_growth 0):

    frac_base ≈ 8.1%  → seats ≈ 1 713
    admit_2026 ≈ 5.2%
    pool_effect ≈ +15 ,  weakening_effect ≈ −7  →  cut_2026 ≈ 229  (net +8)

The +56% pool growth **dominates** the weakening, so the próg **rises**. Candidate 245 clears
221 by +24 and the projected 229 by +16. Sensitivity: seats +10%/+20% → cut ≈ 226 / 223.

**Assumption:** the share of chemia-takers competing for *this specific programme* is stable
year-over-year, and seats are fixed unless you set `seats_growth`. The robust part is the
**decomposition** (direction and rough size of each force); the exact +8 firms up only with
real 2026 data.

---

## 8. Assumptions & limitations (read before trusting a number)

1. **Reference pool = all national extended-level takers**, not the self-selected WUM
   applicant field (who are stronger). So the *absolute* percentile flatters real
   med-competition standing; treat it as an upper bound. (Relative year-on-year *changes*
   are more robust than the absolute level.)
2. **No published joint** → the subject correlation (§3) is an assumption. It mainly affects
   the tails of the index. Stress it.
3. **2026 shape = 2025 shape shifted** (§5) — center moves, spread does not; boundary
   clipping is approximate.
4. **Whole-percent source data** — CKE rounds; sub-percent precision is not available.
5. **Cohort vs graduates** — pool uses broad cohort counts (§1c); distribution shape uses
   this-year-graduate parameters (§1a/§1b). Documented, not hidden.
6. **Monte-Carlo noise** — ~±0.1–0.3 pt on percentiles at N=200k; increase N to tighten.

---

## 9. File map (where each step lives)

| File | Responsibility |
|---|---|
| `cke_data.py` | Sourced 2025 data (stanines + moments), `SubjectStats`, CDF knots, JSON override loader |
| `model.py` | `Marginal` (empirical CDF/inverse-CDF), `Φ`, Gaussian copula `simulate_index`, `JointResult` |
| `wum.py` | WUM index definition, `Candidate`, `analyse_year`, `build_2026` (mean→shift), `project_cutoff` |
| `report.py` | CLI: prints every intermediate number and the takeaway |
| `app_matura.py` | Streamlit UI — all inputs editable (scores, correlations, 2026 means, pool, cut-off) |
| `test_matura.py` | Acceptance tests: stanine reproduction, monotonicity, candidate=245, cut-off identities |

---

## 10. Reproduce every number

```bash
# Full report: per-subject %ile, 2025 & 2026 index %ile, rivals, cut-off projection
python3 src/matura/report.py --pool 21200 --pool2026 33000 --cut2025 221

# Acceptance tests must print ALL PASS
python3 src/matura/test_matura.py

# Physics substitute instead of maths
python3 src/matura/report.py --third fizyka --phys 80

# Once real 2026 data exists, bypass the shift model:
python3 -c "import sys;sys.path.insert(0,'src/matura');from cke_data import dump_template;dump_template('data/matura/2026.json')"
python3 src/matura/report.py --data2026 data/matura/2026.json
```

Hand-check the empirical vs normal gap (proves skew is used, not mean/SD):

```python
import sys, math; sys.path.insert(0,'src/matura')
from cke_data import load_2025
from wum import default_candidate, analyse_year
d=load_2025(); an=analyse_year(d, default_candidate(), n=300000)
s=an.joint.index_samples; m,sd=s.mean(),s.std()
norm=0.5*(1+math.erf((245-m)/sd/math.sqrt(2)))*100
print(f"empirical 245 -> {an.candidate_percentile:.1f}%   normal(mean,sd) -> {norm:.1f}%")
# chemia 85 marginal, empirical vs normal:
st=d.get("chemia"); z=(85-st.mean)/st.sd
print(f"chemia 85 empirical -> {an.candidate_subject_pct['chemia']:.1f}%   "
      f"normal -> {0.5*(1+math.erf(z/math.sqrt(2)))*100:.1f}%")
```

Independent cross-checks you can run without this code:
- **Stanine boundary check:** in each CKE PDF, the top of stanine 7 should map to the 89th
  percentile (0.04+0.07+0.12+0.17+0.20+0.17+0.12 = 0.89). e.g. chemia says 80% → our curve
  returns 89.0% at 80 (`test_matura.py` asserts this).
- **Mean cross-check:** the simulated index mean (~122) should ≈ sum of subject means
  (33+46+43 = 122). It does.
- **Cut-off identity:** projecting with the *same* year and pool must return the input
  cut-off (`test_matura.py` asserts `project(221) ≈ 221`).

---

## 11. Headline results (default inputs)

| Quantity | 2025 | 2026 model (blind) | **2026 actual (real data)** |
|---|---:|---:|---:|
| chemia 85 → percentile | 92.5% | — | 94.6% |
| biologia 88 → percentile | 96.8% | — | 97.3% |
| matematyka 72 → percentile | 86.6% | — | 87.3% |
| **index 245 → percentile** | **96.3%** | **97.3%** | **97.3%** |
| rivals scoring above 245 | ~775 | ~893 | ~864 (pool 31 691) |
| admission cut-off (próg) | 221 (given) | ~229 (+8) | **~228 (+7)** |

Cut-off decomposition (real data): pool growth **+15**, weakening **−8**, net **+7**. The
blind model (+8) landed within 1 point of the actual — a clean out-of-sample validation.
