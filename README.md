# Matura → WUM recruitment percentile (standalone module)

**Unrelated to the DCF/screening pipeline.** Estimates where a Warsaw Medical
University (WUM) candidate ranks, using official CKE 2025 extended-level ("poziom
rozszerzony") results, and models a 2026 population that is larger and weaker without
needing 2026 distributions.

## The question
WUM ranks on a recruitment index = **chemia R + biologia R + (matematyka R _or_ fizyka R)**,
each in %, 1% = 1 point → index ∈ [0, 300]. The brief's candidate (matura 2026):
chemia 85, biologia 88, matematyka 72 → **245 / 300**. Where does 245 sit?

## Method (no black box)
1. **Marginal per subject.** Each subject's score(%)→percentile curve is the empirical
   CDF reconstructed from the official **stanine table** (`skala staninowa`). CKE does
   not publish a percent-by-percent histogram, but it does publish, per subject, the 9
   stanine score-bands that each hold a fixed population fraction
   (4/7/12/17/20/17/12/7/4 %). Those bands **are** published percentile boundaries. We
   interpolate the curve between them — which respects each subject's real skew (e.g.
   matematyka R: modal 0 %, mean 33 %) far better than a normal fit.
2. **Joint index.** The sum's distribution depends on how subjects co-move — CKE
   publishes no joint. We combine the marginals with a **Gaussian copula** whose
   correlation matrix is an explicit, tunable assumption (bio–chem strong, math weaker).
   Monte-Carlo → the index distribution → the percentile of 245.
3. **2026 without 2026 data.** Shift each 2025 marginal horizontally by the announced
   change in its mean (biologia 46→41 ⇒ −5; chemia 43→41 ⇒ −2), clipped to [0,100].
   This preserves the published shape while reproducing the mean drop — the signature of
   a larger, weaker cohort. The +30 % cohort growth does not move a percentile (scale-free)
   but scales the absolute rival count, reported separately.

## Result (default inputs, official 2025 data)
| | chemia 85 | biologia 88 | matematyka 72 | index 245 |
|---|---|---|---|---|
| percentile among 2025 R takers | 92.5 % | 96.8 % | 86.6 % | **96.3 %** |
| percentile in 2026 model (weaker+larger) | | | | **97.3 %** |

Rivals scoring higher stay ~flat (2025 ≈ 744 → 2026 ≈ 716 in the chemia-R-sized pool):
the +30 % cohort is offset by its weakness.

**Caveat, stated everywhere:** the reference pool is *all* national extended-level
takers, not the self-selected WUM applicant field (who are stronger), so true
med-competition standing is somewhat lower. The 2026 number is a **model** — stress it
via the correlation, mean, and pool inputs.

## Cut-off (próg) projection
A cut-off is the score of the last admitted candidate, so #(applicants ≥ cut) = #seats.
Given the 2025 cut-off, we hold seats fixed and read the score at that same headcount in
the larger/weaker 2026 distribution — separating two opposing forces: a bigger pool pushes
the cut UP, a weaker field pulls it DOWN. Worked example (2025 cut = 221, chemia pool
21,200→33,000 = +56%, means bio 46→41 / chem 43→41):

    pool-growth effect +15,  weakening effect −7  →  projected 2026 cut ≈ 229 (+8)

The +56% pool growth dominates the weakening, so the cut *rises*. A 245-pt candidate clears
221 by +24 and the projected 229 by +16.

## Run
```bash
python3 src/matura/report.py                       # default candidate + 2026 model
python3 src/matura/report.py --chem 85 --bio 88 --math 72
python3 src/matura/report.py --third fizyka --phys 80
python3 src/matura/report.py --pool 21200 --pool2026 33000 --cut2025 221   # cut-off projection
python3 src/matura/report.py --data2026 data/matura/2026.json   # once real 2026 data exists
python3 src/matura/test_matura.py                  # acceptance tests → ALL PASS
streamlit run src/matura/app_matura.py             # stage-2 UI, all inputs editable (port 8502)
```

## Files
- `cke_data.py` — sourced 2025 stats (stanines + moments), dataclasses, JSON override loader.
- `model.py` — empirical marginal (stanine inverse-CDF), Gaussian copula MC, percentile engine.
- `wum.py` — WUM index definition, candidate, 2025 vs 2026 analysis, mean→shift translation.
- `report.py` — CLI report (leads with the takeaway; shows every intermediate number).
- `app_matura.py` — Streamlit UI with editable candidate / correlations / 2026 means / pool.
- `test_matura.py` — sanity/acceptance tests (stanine reproduction, monotonicity, candidate = 245).

## Sources (official CKE / OKE, 2025 exam)
- Stanines (all subjects): CKE *Skale staninowe wyników — egzamin maturalny 2025*.
- Parameters (mean/median/SD/modal/N): national subject reports, oke.poznan.pl
  (`em2023_<subject>_raport_kraj_2025.pdf`).
- Total 2025 graduates: 255 517 (*Sprawozdanie ogólne 2025*).
- Full URLs are in the docstring of `cke_data.py` and the `source` field of each subject.
