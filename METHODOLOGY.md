# Methodology — WUM matura percentile & cut-off module

A complete, verifiable account of how this module turns published CKE 2025 data into
(a) a candidate's percentile, (b) a modelled 2026 percentile, and (c) a projected 2026
admission cut-off. Every number below is reproducible from the commands in §10, and every
input is traceable to an official source in §1. Nothing here is a black box.


---

## 0. The object we are ranking

WUM (Warszawski Uniwersytet Medyczny) ranks candidates on a **recruitment index**:

    index = chemia_R + biologia_R + max(matematyka_R, fizyka_R)

each subject a matura **extended-level** ("poziom rozszerzony") result in **%**, with the
rule **1% = 1 point**, so `index ∈ [0, 300]`. The third slot takes the **better of**
mathematics or physics (§3a). The worked candidate sat only mathematics: chemia 85,
biologia 88, matematyka 72 → **index = 245** (the *field*, however, gets the best-of-two
uplift, so a candidate who sat one subject ranks slightly below the modelled field).

> **Three modelling corrections (2026-07 revision).** This revision fixes three issues
> that had overstated the candidate and understated the field. Each is documented in the
> section noted and covered by `test_matura.py`:
> 1. **Third-subject reference population** (§2b) — maths/physics R nationally is dominated
>    by *non-med* candidates; the third slot is now ranked against a **med-pool** marginal.
> 2. **Copula family** (§3) — Gaussian → **Student-t**, which (unlike Gaussian) has non-zero
>    upper-tail dependence, exactly where a top-3% cut-off lives.
> 3. **Third slot = max(math, phys)** (§3a) — an order statistic on a **4-variable** copula,
>    not a single chosen marginal.

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

### 1b'. Centyle tables — the **primary** object (2025 & 2026)
CKE also publishes, per subject, the **skala centylowa** ("Skale centylowe wyników"): a
fine table giving, for each score(%), its **centyl** = `P(result ≤ score)·100`. This is the
published score→percentile curve *itself* at ~1-point resolution — no band interpolation.
We store it per subject (`cke_data.py` → `centile`, and `data/matura/2026.json`) and use it
as the primary empirical object whenever present; the stanine table (§1b) is the fallback.
The centyle curve is strictly finer: e.g. **matematyka 2025 at 72 reads 91** from the centyle
curve vs ~86.6 from 9-knot stanine interpolation — the coarse object mis-stated it by ~4 pts.

Sources: CKE *Skale centylowe wyników — egzamin maturalny* **2025** (`…EM25 CENTYLE.pdf`,
2025-07-08) and **2026** (`…EM26 CENTYLE.pdf`, 2026-07-08); "Wszystkie przedmioty", all
national takers.

### 1b. Stanine tables — the fallback object
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
Official CKE extended-level counts, **this-year graduates** — the *same basis for both
years* (§1a for 2025; *Wstępne informacje EM26* Tabela 2 for 2026), so growth is like-for-like:

| Subject (R) | 2025 N | 2026 N | change |
|---|---:|---:|---:|
| matematyka | 67 384 | 88 856 | +32% |
| biologia   | 41 718 | 67 312 | +61% |
| chemia     | 20 340 | 31 691 | **+56%** |
| fizyka     | 13 961 | 19 364 | +39% |

Overall matura cohort grew ~+30%; the med-binding **chemia** cohort grew **+56%** (see §6).

> **One basis, on purpose.** Growth is only meaningful like-for-like. We use the CKE
> **this-year-graduate** count for *both* years and for *both* pool sizing and distribution
> shape — 20 340 → 31 691 = **+56%**. Do **not** mix bases: pairing the older *broad*
> cohort figure for 2025 (≈21 200, which also counts repeat/adult takers) with the 2026
> this-year-graduate count (31 691) wrongly reads **+49%**. (The broad basis is internally
> consistent too — ≈21 200 → ≈33 000 is also +56% — but we standardise on the this-year
> count because it is the number actually in the data files, from one source definition.)

---

## 2. Per-subject marginal: score → percentile (the empirical CDF)

We build each subject's cumulative distribution function (CDF) by **linear interpolation
between the published knots**, anchored at (0, 0). With the **centyle** curve (primary,
§1b') the knots are the ~57 published `(score, centyl/100)` points; with the **stanine**
fallback (§1b) they are the 9 `(stanine_upper, cum)` points:

    knots_x = scores                        # from centyle, else stanine_upper
    knots_y = cumulative fractions          # centyl/100, else stanine cum
    percentile(score) = 100 · interp(score; knots_x → knots_y)

This respects each subject's real **skew** (e.g. matematyka R: modal 0%, mean 33% — heavily
right-skewed) rather than assuming a symmetric bell curve. Code: `model.py` → `Marginal`,
`cke_data.py` → `SubjectStats.cdf_knots`.

### Worked example — candidate subjects (hand-checkable against the published centyle table)
Reading the 2025 centyle curve directly (`test_marginal_reproduces_centile_curve` asserts the
CDF hits every published knot):

    chemia 85 → 94   ·   biologia 88 → 98   ·   matematyka 72 → 91   ·   fizyka 80 → 78

(The coarser stanine fallback returns chemia 85 → 92.5, matematyka 72 → 86.6 — up to ~4 pts
off; the finer centyle numbers above are authoritative.) For 2026 the same lookup gives
chemia 85 → 95, biologia 88 → 99, matematyka 72 → 87, fizyka 80 → 90.

### Sampling (inverse CDF)
To simulate a candidate we invert the curve: draw `u ~ Uniform(0,1)`, then
`score = interp(u; knots_y → knots_x)`. Code: `Marginal.quantile`.

---

## 2b. Third-subject **med-pool** marginal (the reference-population fix)

The national marginal from §2 is the right reference for **chemia** and **biologia** —
chemia-R is essentially the med pool (§6), and bio-R is med-heavy. It is the **wrong**
reference for the **third slot**. National **matematyka R** (N≈88.9k, mean 37%) is
dominated by **non-med** candidates (engineering, economics, CS); a med applicant's maths
is drawn from maths-R *conditioned on also taking bio-R and chem-R*, a sub-population that
sits well to the right. Ranking matematyka 72 against the raw national pool (→ 87th
percentile in 2026, from the published centyle curve) **overstates** the candidate and
**understates** the field.

**Fix.** We build a **distinct med-pool marginal** for the third subject, not the raw
national one. Cleanest data-grounded route: reconstruct it from published admitted-cohort
subject profiles (WUM and peers publish last-admitted subject scores and admitted
distributions). **Interim proxy (current default):** a max-entropy **reweight** of the
national marginal to a target mean uplifted by the estimated national→med-pool gap:

    gap = { matematyka: +13, fizyka: +8 } pts of mean     # cke_data.THIRD_MEDPOOL_GAP

The reweight exponentially tilts the stanine-segment masses to hit `base_mean + gap`,
keeping the same support [0,100] (no boundary pile-up). Both the CDF (percentile) and the
sampler (quantile) read the tilted curve, so candidate standing and the simulated field are
consistent. Code: `Marginal(tilt_shift=…)`, selected in `wum.analyse_year` (`medpool=True`).
The gaps are **interim estimates** — overridable per-year via the JSON loader
(`"medpool_gap": {…}`) and via the app slider — and are flagged to be replaced with
admitted-cohort data when in hand (`cke_data.THIRD_MEDPOOL_SOURCE`).

**Delta this produces (documented, `test_medpool_third_delta`):**

| matematyka 72 → percentile | national marginal (centyle) | med-pool marginal |
|---|---:|---:|
| 2025 | 91.0% | **80.7%** (−10.3) |
| 2026 | 87.0% | **76.0%** (−11.0) |

Physics (fizyka) gets the smaller +8 gap — physics-R is already more self-selected/able, so
the med vs all-comers gap is narrower. Setting `medpool=False` recovers the national figure.

---

## 3. Joint distribution of the index (Student-t copula)

The index is a **sum of subjects**, so its distribution depends on how the subjects
**co-move** — a joint distribution CKE does **not** publish. We combine the empirical
marginals with a **copula**: the marginals stay exactly as in §2 (skew preserved), and only
the *dependence* is modelled.

**Family: Student-t, not Gaussian.** The admission cut-off lives in the **top ~3%**. A
**Gaussian** copula has **zero upper-tail dependence** (λ_upper = 0): it *decouples* joint
extremes exactly where the cut-off is set, understating candidates who are high in **all**
subjects. A **Student-t** copula has **non-zero** upper-tail dependence controlled by the
degrees of freedom **ν** — lower ν ⇒ heavier joint tails; ν → ∞ recovers the Gaussian. We
default to **ν = 6** (5–8 is reasonable for co-moving exam scores); it is a slider in the app.

Procedure (`model.py` → `simulate_index`), subject order `[chemia, biologia, matematyka, fizyka]`:

1. Correlation matrix `R`. Defaults (`default_corr`, tunable): `bio–chem = 0.60`,
   `chem–third = 0.50`, `bio–third = 0.45`, `math–phys = 0.60`.
2. Cholesky factor `L` with `R = L·Lᵀ` (nudged onto the PSD cone if a hand-entered `R`
   is not positive-definite).
3. Draw `Z ~ N(0, I)` of shape `(N, k)`; correlate: `X = Z · Lᵀ`.
4. **t step:** draw `W ~ χ²(ν)` and form `T = X / √(W/ν)` (now multivariate-t); map to
   uniforms with the **Student-t CDF** `U = t_ν(T)`. (ν = None ⇒ `U = Φ(X)`, the Gaussian
   copula.) Both CDFs are computed **without scipy**: Φ via `math.erf`; `t_ν` via a small
   vectorised **regularized-incomplete-beta** routine (`_betai`/`_betacf`, continued
   fraction), validated against reference values in `test_t_cdf_matches_reference`.
5. Invert each marginal: `score_j = Q_j(U_j)`; combine (§3a).

`N = 200 000` samples, fixed `seed = 12345` (reproducible; `test_matura.py` checks that same
seed → identical output).

**What ν buys, verified (`test_student_t_upper_tail_monotone_in_nu`):** at fixed
correlations, lowering ν **raises the index upper tail** — index p99 is strictly monotone in
ν (ν=3: 285 → ν=8: 282 → ν=40: 281 → Gaussian: 280) and the projected 2026 cut-off moves
**up** under heavier tails. Correlation and ν are the two dependence assumptions; both are
sliders/arguments so you can stress them. The marginals carry **no** normality assumption.

### 3a. Third slot = **max(matematyka, fizyka)** (a 4-variable copula)

WUM takes the **better of** maths or physics, so the third contribution is an **order
statistic**, not a single marginal. We therefore draw a **4-variable** copula over
`[chemia, biologia, matematyka, fizyka]` and combine:

    index = chemia + biologia + max(matematyka, fizyka)

Code: `simulate_index(combine=…)` with `wum._max_third_combine`; enabled by
`analyse_year(max_third=True)` (default). The 4×4 correlation is built from the three core
sliders by `wum.wum_corr` (the third-slot correlations apply to both maths and physics;
`math–phys = 0.60` shapes the latent max).

**Approximation stated plainly:** few candidates actually sit **both** maths-R and
physics-R, so the joint `(math, phys)` is a *latent* construct representing "best available
third subject." The max on this latent pair is the field's best-of uplift. Effect, verified
(`test_max_third_uplift`): the field index **mean rises** (≈135 → ≈153) and its **upper tail
rises**, so a fixed candidate score ranks **slightly lower** than under a single-third model.
The candidate keeps their own chosen third subject (they did not sit the other one).

---

## 4. Candidate percentile & rival count

Given `N` simulated indices and the candidate index `v = 245`:

    percentile(v) = 100 · mean( index_samples ≤ v )
    rivals_above  = mean( index_samples > v ) · pool

`pool` = the relevant applicant population (see §6). Code: `JointResult.percentile_of`,
`JointResult.rank_above`.

**2025 result (default model — centyle marginals §1b', med-pool third §2b, Student-t ν=6 §3,
max-third §3a):** index mean ≈ 150, median ≈ 150, SD ≈ 63, p99 ≈ 282; **245 → 93.2%**;
rivals above ≈ 1 380 in a 20 340 pool. The stronger field (med-pool third + best-of-two +
tail dependence) pulls this below the old raw-national-and-Gaussian figure of 96.3% — that
number overstated the candidate, which is exactly what this revision corrects.

**Sanity vs a normal approximation (why skew matters):** the empirical percentile still
differs from a naive `Φ((245−mean)/sd)` because the index is not Gaussian (right-skewed body,
tail-dependent top). Reproduce with the snippet in §10.

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
> (Those percentile/cut-off figures were computed under the *pre-2026-07 model* —
> raw-national third subject, single third marginal, Gaussian copula. The shift-model vs
> real-data validation is about the 2026 **marginal shapes** and is unaffected; the
> current default model's headline numbers are in §11.)
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
who can be in the competition is capped by the **smallest** cohort — **chemia** (31 691 <
67 312 bio < 88 856 math in 2026). Nearly everyone taking chemia-R is on the med track and
also takes bio-R, so **chemia cohort ≈ med-applicant pool**. Therefore:

- `pool_2025 = 20 340`, `pool_2026 = 31 691` (both CKE this-year-graduate counts, §1c) →
  **pool growth = +56%** (not the +30% overall). Keep both years on this one basis — mixing
  in the older broad 2025 figure (≈21 200) understates growth to +49% (§1c).
- Percentile (§4) is **scale-free** — pool size does not affect it. Pool only scales
  **absolute counts** (rivals, and the cut-off headcount in §7).

Consequence: rivals-above are ≈ **1 380 (2025)** → **1 311 (2026)** — a slight *fall*, because
the ~+56% more people are offset by the weaker + med-corrected field. Percentile still
improves (93.2% → 95.9%). Both facts are true; they answer different questions.

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

**Worked result** (default model on real 2026 data; cut_base = 221, pool 20 340→31 691,
seats_growth 0):

    frac_base ≈ 14.7%  → seats ≈ 2 990
    admit_2026 ≈ 9.4%
    pool_effect ≈ +15 ,  weakening_effect ≈ −13  →  cut_2026 ≈ 223  (net +2)

The +56% pool growth and the weaker + med-corrected field **nearly cancel**, so the próg
barely moves. Candidate 245 clears 221 by +24 and the projected 223 by +22. Sensitivity:
seats +10%/+20% → cut ≈ 220 / 218 (more seats can only lower the cut).

**Assumption:** the share of chemia-takers competing for *this specific programme* is stable
year-over-year, and seats are fixed unless you set `seats_growth`. The robust part is the
**decomposition** (direction and rough size of each force); the exact +8 firms up only with
real 2026 data.

---

## 8. Assumptions & limitations (read before trusting a number)

1. **Reference pool.** The **third subject** is now med-pool-corrected (§2b), but **chemia &
   biologia are still ranked vs all national extended-level takers**. chem/bio-R are already
   med-heavy, so the residual flattery is much smaller than the raw-national third subject was
   — but **non-zero**. The absolute percentile is still a mild upper bound on true
   med-competition standing; year-on-year *changes* are the robust part.
1a. **Med-pool gaps are interim estimates** (§2b: matematyka +13, fizyka +8 pts of mean),
   sized to the national→med-pool mean gap pending published admitted-cohort subject
   profiles. They are the single biggest third-subject lever — overridable via JSON/slider.
2. **No published joint** → the subject **correlation and ν** (§3) are assumptions. They
   drive the tails of the index (where the cut-off lives). Stress both.
2a. **max(math, phys) uses a latent joint** (§3a): few candidates sit both subjects, so the
   best-of-two is a modelling construct for "best available third subject."
3. **2026 shape = 2025 shape shifted** (§5, what-if model only) — center moves, spread does
   not; boundary clipping is approximate.
4. **Whole-percent source data** — CKE rounds; sub-percent precision is not available.
5. **One cohort basis** — pool sizing and distribution shape both use the CKE
   **this-year-graduate** counts (§1c), the same basis for 2025 and 2026, so growth is
   like-for-like (+56%). Do not mix in the older broad 2025 count (that reads a spurious
   +49%). Documented, not hidden.
6. **Monte-Carlo noise** — ~±0.1–0.3 pt on percentiles at N=200k; increase N to tighten.

---

## 9. File map (where each step lives)

| File | Responsibility |
|---|---|
| `cke_data.py` | Sourced 2025 data (centyle + stanines + moments), `SubjectStats`, `cdf_knots` (centyle-primary, stanine-fallback), JSON override loader, `THIRD_MEDPOOL_GAP` (§2b) |
| `model.py` | `Marginal` (empirical CDF/inverse-CDF + med-pool `tilt_shift`), `Φ`, Student-t CDF (`_betai`/`_t_cdf`, no scipy), t/Gaussian copula `simulate_index` (`nu`, `combine`), `JointResult` |
| `wum.py` | WUM index = chem+bio+max(math,phys), `wum_corr` (4×4), `Candidate`, `analyse_year` (`nu`/`medpool`/`max_third`), `build_2026`, `project_cutoff` |
| `report.py` | CLI: prints every intermediate number and the takeaway |
| `app_matura.py` | Streamlit UI — all inputs editable (scores, correlations, 2026 means, pool, cut-off) |
| `test_matura.py` | Acceptance tests: stanine reproduction, monotonicity, candidate=245, cut-off identities |

---

## 10. Reproduce every number

```bash
# Full report: per-subject %ile, 2025 & 2026 index %ile, rivals, cut-off projection
python3 src/matura/report.py --pool 20340 --pool2026 31691 --cut2025 221

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
- **Mean cross-check:** the per-subject empirical means recovered from the fine centyle
  curve sit within ~1–2 pts of CKE's published means (e.g. 2025 matematyka 31.3 vs published
  33; the coarse integer centyl rounds the mean marginally low). The **default** index mean
  is higher (~150 in 2025) than the bare sum of subject means because the med-pool third
  (§2b) and best-of-two (§3a) both lift the third-subject contribution; reproduce a plain
  ~122 baseline with `report.py --no-medpool --no-max-third --gaussian`.
- **Cut-off identity:** projecting with the *same* year and pool must return the input
  cut-off (`test_matura.py` asserts `project(221) ≈ 221`).

---

## 11. Headline results (default model: centyle marginals §1b' · med-pool third §2b · Student-t ν=6 §3 · max-third §3a)

| Quantity | 2025 | **2026 actual (real data)** |
|---|---:|---:|
| chemia 85 → percentile (national centyle) | 94.0% | 95.0% |
| biologia 88 → percentile (national centyle) | 98.0% | 99.0% |
| matematyka 72 → percentile **(med-pool)** | **80.7%** | **76.0%** |
| matematyka 72 → percentile (raw national centyle, for contrast) | 91.0% | 87.0% |
| **index 245 → percentile** | **93.2%** | **95.9%** |
| rivals scoring above 245 | ~1 380 (pool 20 340) | ~1 311 (pool 31 691) |
| admission cut-off (próg) | 221 (given) | **~223 (+2)** |

Both pools are CKE **this-year-graduate** chemia counts (§1c), so growth is a clean **+56%**.
Cut-off decomposition (real data): pool growth **+15**, weakening **−13**, net **+2**.

**What changed, and why.** Four corrections separate this from the original raw-national /
single-third / Gaussian / stanine model (which read index 245 → 96.3% / 97.3%):
1. **Centyle marginals (§1b')** replace 9-knot stanine interpolation with the published
   ~57-knot percentile curve — authoritative per-subject percentiles (e.g. matematyka 2025
   at 72: 86.6 → **91**; biologia 88: 96.8 → **98**), which by themselves *raise* the
   candidate.
2. **Med-pool third (§2b)** ranks maths/physics against bio+chem co-takers, dropping the
   third-subject percentile ~10–11 pts — the largest single correction.
3. **max(math, phys) (§3a)** and 4. **Student-t tail dependence (§3)** strengthen the field.

Net: the index sits at **93.2% (2025) / 95.9% (2026)** — a **top-5-to-7%** band, below the
old top-3% figure the coarser/overstated model produced. The candidate still clears the
projected 2026 cut-off (~223) comfortably by **+22**. All figures reproduce from
`report.py … --data2026 data/matura/2026.json` and are locked by `test_matura.py`.
