# Matura → WUM recruitment percentile (standalone module)

**Unrelated to the DCF/screening pipeline.** Estimates where a Warsaw Medical
University (WUM) candidate ranks, using official CKE extended-level ("poziom
rozszerzony") results for **2025 and 2026**.

> **2026 update (2026-07-08):** the official 2026 stanine curves are now published and
> ingested ([`../../data/matura/2026.json`](../../data/matura/2026.json)). The app and CLI
> default to this **real 2026 data**. A blind forecast made *before* any 2026 distribution
> existed (the "shift-model" below) was then confirmed by the actuals for the 2026 marginal
> *shapes*. The shift-model remains available as a what-if scenario tool. (The 97.3% /
> ~228 figures from that validation were under the pre-2026-07 field model; the current
> default model's headline is in the result table below and in `METHODOLOGY.md` §11.)

> **Modelling revision (2026-07):** three corrections now sharpen the field model —
> (1) the third subject is ranked against a **med-pool** marginal, not the raw national
> maths/physics pool (dominated by non-med candidates); (2) the copula is **Student-t**
> (upper-tail dependence), not Gaussian; (3) the third slot is **max(math, phys)** via a
> 4-variable copula. Together they place the 245-pt candidate more realistically (see the
> updated result table). Details in [`METHODOLOGY.md`](METHODOLOGY.md) §2b, §3, §3a.

## The question
WUM ranks on a recruitment index = **chemia R + biologia R + max(matematyka R, fizyka R)**,
each in %, 1% = 1 point → index ∈ [0, 300]. The brief's candidate (matura 2026):
chemia 85, biologia 88, matematyka 72 → **245 / 300**. Where does 245 sit?

> **Full, verifiable derivation:** see [`METHODOLOGY.md`](METHODOLOGY.md) — formulas,
> data provenance with source URLs, worked examples, assumptions/limitations, and
> copy-paste commands to reproduce every number.

## Method (no black box)
1. **Marginal per subject.** Each subject's score(%)→percentile curve is the empirical
   CDF read directly from CKE's published **centyle table** (`skala centylowa`) — the fine
   ~1-point-resolution score→percentile curve for every subject and both years (2025 &
   2026). (The coarser 9-band **stanine** table is kept as a fallback; the centyle curve is
   strictly finer, e.g. matematyka 2025 at 72 reads **91** from centyle vs ~86.6 from
   9-knot stanine interpolation.) This respects each subject's real skew (e.g. matematyka R:
   modal 0 %, mean 33 %) with no normal-curve assumption.
   The **third subject** (maths/physics) is additionally reweighted to the **med pool**
   (bio+chem co-takers) — national maths-R is dominated by non-med candidates, so the raw
   national percentile overstates a med applicant (matematyka 72: national 87.3% →
   med-pool 75.6% in 2026).
2. **Joint index.** The index's distribution depends on how subjects co-move — CKE
   publishes no joint. We combine the marginals with a **Student-t copula** (tunable
   correlation **and** degrees-of-freedom ν): unlike a Gaussian copula, it has non-zero
   **upper-tail dependence**, so candidates high in *all* subjects co-occur — the region a
   top-3% cut-off lives in. The third slot is the **max of maths and physics** (a 4-variable
   copula), the real WUM rule. Monte-Carlo → the index distribution → the percentile of 245.
3. **2026.** When real 2026 stanine data is present (default), its curves are built the
   same way as (1) — no model. As a scenario alternative, the **what-if model** shifts each
   2025 marginal horizontally by an assumed change in its mean (biologia 46→41 ⇒ −5; chemia
   43→41 ⇒ −2), clipped to [0,100]; this preserves the published shape while reproducing a
   mean drop — the signature of a larger, weaker cohort. The +56 % chemia-cohort growth does
   not move a percentile (scale-free) but scales the absolute rival count, reported separately.

## Result (default model — official real 2026 centyle data; Student-t ν=6, med-pool third, max-third)
| | chemia 85 | biologia 88 | matematyka 72 | index 245 |
|---|---|---|---|---|
| percentile among 2025 R takers | 94.0 % | 98.0 % | **80.7 %** (med-pool) | **93.2 %** |
| percentile among **2026** R takers (real) | 95.0 % | 99.0 % | **76.0 %** (med-pool) | **95.9 %** |

chem/bio percentiles are read straight off CKE's published centyle curve. matematyka's *raw
national* centyle percentile (91 % / 87 %) is shown in the app for contrast; the med-pool
figures above are the correct reference for a med applicant. The index percentile sits below
the old raw-national-Gaussian-stanine headline (96.3 % / 97.3 %) — that number overstated the
candidate. Rivals scoring higher: 2025 ≈ 1 380 (pool 20 340) → 2026 ≈ 1 311 (pool 31 691) —
both pools are CKE **this-year-graduate** chemia counts, so growth is a clean **+56%**.

**Caveat, stated everywhere:** the third subject is med-pool-corrected, but **chemia &
biologia are still ranked vs all national extended-level takers** — they are already
med-heavy, so the residual flattery is small but non-zero; true med-competition standing is
somewhat lower still. The med-pool gaps and ν are **tunable assumptions** — stress them via
the sliders. Year-over-year *change* is the robust part.

## Cut-off (próg) projection
A cut-off is the score of the last admitted candidate, so #(applicants ≥ cut) = #seats.
Given the 2025 cut-off, we hold seats fixed and read the score at that same headcount in
the larger/weaker 2026 distribution — separating two opposing forces: a bigger pool pushes
the cut UP, a weaker field pulls it DOWN. Worked example (2025 cut = 221, chemia pool
**20,340→31,691** = +56%, same this-year-graduate basis both years, real 2026 data):

    pool-growth effect +15,  weakening effect −13  →  projected 2026 cut ≈ 223 (+2)

Under the richer field model the two forces nearly cancel (pool growth pushes up, the
stronger med-pool/best-of-two field weakens down), so the cut barely moves. A 245-pt
candidate clears 221 by +24 and the projected 223 by +22.

## Run
```bash
python3 src/matura/report.py                       # default candidate + 2026 model
python3 src/matura/report.py --chem 85 --bio 88 --math 72
python3 src/matura/report.py --third fizyka --phys 80
python3 src/matura/report.py --pool 20340 --pool2026 31691 --cut2025 221   # cut-off projection
python3 src/matura/report.py --data2026 data/matura/2026.json   # once real 2026 data exists
python3 src/matura/test_matura.py                  # acceptance tests → ALL PASS
streamlit run src/matura/app_matura.py             # stage-2 UI, all inputs editable (port 8502)
```

## Files
- `cke_data.py` — sourced 2025 stats (centyle curves + stanines + moments), dataclasses,
  `cdf_knots` (centyle-primary / stanine-fallback), JSON override loader, `THIRD_MEDPOOL_GAP`.
- `model.py` — empirical marginal (stanine inverse-CDF + med-pool reweight), Student-t /
  Gaussian copula MC (t-CDF via no-scipy incomplete beta), percentile engine.
- `wum.py` — WUM index = chem+bio+max(math,phys), 4×4 correlation, 2025 vs 2026 analysis.
- `report.py` — CLI report (leads with the takeaway; shows every intermediate number).
- `app_matura.py` — Streamlit UI with editable candidate / correlations / 2026 means / pool.
- `test_matura.py` — sanity/acceptance tests (stanine reproduction, monotonicity, candidate = 245).

## Sources (official CKE / OKE)
- **Centyle** (all subjects, primary): CKE *Skale centylowe wyników — egzamin maturalny*
  **2025** & **2026** (`…EM25/EM26 CENTYLE.pdf`, published 8 July of each year).
- Stanines (fallback): CKE *Skale staninowe wyników — egzamin maturalny 2025/2026*.
- Parameters (mean/median/SD/modal/N): national subject reports, oke.poznan.pl
  (`em2023_<subject>_raport_kraj_2025.pdf`); 2026 means from *Wstępne informacje EM26* Tab. 2.
- Total 2025 graduates: 255 517 (*Sprawozdanie ogólne 2025*).
- Full URLs are in the docstring of `cke_data.py` and the `source` field of each subject.
