"""CKE 2025 matura data — the empirical foundation for the percentile module.

This module is *unrelated* to the DCF / screening pipeline. It holds the official,
sourced 2025 extended-level ("poziom rozszerzony") result statistics for the four
subjects relevant to Warsaw Medical University (WUM) recruitment, and a loader that
lets you override / add years (e.g. 2026) from a JSON file without touching code.

Why these numbers and not a live scrape:
    CKE publishes, per subject, two score->percentile objects plus moments:
    (a) the "skala centylowa" (centyle) — a fine, ~1-point-resolution table mapping each
        score(%) to its percentile (centyl). This is the PRIMARY empirical object when
        present: it is the published score->percentile curve itself, no interpolation of
        coarse bands needed.
    (b) the "skala staninowa" (stanine) — a 9-band table mapping score ranges to fixed
        population fractions (4/7/12/17/20/17/12/7/4 %). Kept as a FALLBACK for subjects/
        years where the centyle table is not in hand; the 9 upper bounds are themselves
        published percentile boundaries.
    (c) distribution parameters (mean/median/SD/N), used only for display and to size the
        what-if 2026 shift.
    The centyle table is strictly finer than the stanine one (e.g. matematyka 2025 at 72
    reads 91 from the centyle curve vs ~86.6 from 9-knot stanine interpolation — the
    coarser object mis-stated it by ~4 pts). Every figure below carries its source URL.

Sources (all official CKE / OKE, 2025 exam):
  - Centyle (all subjects): CKE "Skale centylowe wyników — egzamin maturalny 2025":
    https://cke.gov.pl/images/_EGZAMIN_MATURALNY_OD_2023/Informacje_o_wynikach/2025/20250708%20Wst%C4%99pne%20informacje%20o%20wynikach%20EM25%20CENTYLE.pdf
  - Stanines (all subjects): CKE "Skale staninowe wyników — egzamin maturalny 2025":
    https://cke.gov.pl/images/_EGZAMIN_MATURALNY_OD_2023/Informacje_o_wynikach/2025/20250708%20Wstepne%20informacje%20o%20wynikach%20EM25%20STANINY%20POL.pdf
  - Parameters (mean/median/SD/modal/N): national subject reports (raport krajowy):
    matematyka https://www.oke.poznan.pl/files/cms/882/em2023_matematyka_raport_kraj_2025.pdf
    biologia   https://www.oke.poznan.pl/files/cms/882/em2023_biologia_raport_kraj_2025.pdf
    chemia     https://www.oke.poznan.pl/files/cms/882/em2023_chemia_raport_kraj_2025.pdf
    fizyka     https://www.oke.poznan.pl/files/cms/882/em2023_fizyka_raport_kraj_2025.pdf
  - Total graduates 2025: 255 517 (Sprawozdanie ogólne 2025).
Note: CKE reports these to whole-percent precision (no decimals published).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json

# Canonical national stanine population fractions (sum = 1.00). Same for every subject.
STANINE_BANDS = (0.04, 0.07, 0.12, 0.17, 0.20, 0.17, 0.12, 0.07, 0.04)


@dataclass(frozen=True)
class SubjectStats:
    """One subject at extended level for one year.

    stanine_upper: the UPPER score (%) of each of the 9 stanine classes, in order.
        Paired with STANINE_BANDS these give the empirical CDF knots:
        cumulative fraction at score `stanine_upper[i]` == sum(BANDS[:i+1]).
        (For matematyka 2025 CKE merged stanines 8 & 9 into one printed range
         78%–100%; we encode both boundaries at 100 so the 0.89->1.00 step is a
         single segment — mathematically consistent.)
    """
    subject: str          # canonical key: 'biologia' | 'chemia' | 'matematyka' | 'fizyka'
    year: int
    n: int                # liczba zdających (extended level)
    mean: float           # średnia, %
    median: float         # mediana, %
    sd: float             # odchylenie standardowe, %
    modal: float          # modalna, %
    stanine_upper: tuple  # 9 upper-score boundaries, % (fallback empirical object)
    source: str = ""      # provenance note
    centile: tuple = ()   # optional ((score%, centyl), …): the PRIMARY empirical object
                          # when present (finer than stanine). centyl = P(result <= score)*100.

    def cdf_knots(self):
        """Return (scores, cum) monotone knots for the empirical CDF, anchored at (0,0).

        Uses the published centyle curve when available (finer, ~1-point resolution),
        else reconstructs from the 9-band stanine table.
        """
        if self.centile:
            scores = [0.0] + [float(sc) for sc, _ in self.centile]
            cumc = [0.0] + [float(pc) / 100.0 for _, pc in self.centile]
        else:
            cum = []
            acc = 0.0
            for b in STANINE_BANDS:
                acc += b
                cum.append(round(acc, 4))
            # anchor a (0,0) point so scores below the first stanine top interpolate sanely
            scores = [0.0] + list(self.stanine_upper)
            cumc = [0.0] + cum
        # de-duplicate repeated scores (stanine 100,100; centyle flat top): keep last cum
        s_out, c_out = [scores[0]], [cumc[0]]
        for s, c in zip(scores[1:], cumc[1:]):
            if s <= s_out[-1]:
                c_out[-1] = c          # same score, take the higher cumulative
            else:
                s_out.append(s); c_out.append(c)
        return s_out, c_out


# ---------------------------------------------------------------------------
# Built-in official 2025 dataset (verbatim, sourced above).
# ---------------------------------------------------------------------------
_RAPORT = "https://www.oke.poznan.pl/files/cms/882/em2023_{}_raport_kraj_2025.pdf"
_STAN = "CKE skala staninowa 2025"
_CENT = "CKE skala centylowa 2025 (Wstepne informacje EM25 CENTYLE, 2025-07-08)"

# Published centyle curves (score%, centyl) — the primary empirical object (see module doc).
# Verbatim from CKE "Skale centylowe wyników — egzamin maturalny 2025", per subject.
_CENT2025 = {
    "matematyka": ((0,7),(2,11),(4,17),(6,21),(8,25),(10,28),(12,31),(14,33),(16,36),(18,39),(20,41),(22,44),(24,46),(26,49),(28,51),(30,54),(32,56),(34,59),(36,61),(38,63),(40,65),(42,67),(44,70),(46,72),(48,74),(50,75),(52,77),(54,79),(56,81),(58,82),(60,84),(62,85),(64,87),(66,88),(68,89),(70,90),(72,91),(74,92),(76,93),(78,94),(80,95),(82,96),(84,97),(86,97),(88,98),(90,99),(92,99),(94,99),(96,100),(98,100),(100,100)),
    "biologia": ((0,1),(2,1),(3,1),(5,1),(7,2),(8,3),(10,4),(12,6),(13,8),(15,10),(17,13),(18,16),(20,18),(22,21),(23,24),(25,26),(27,28),(28,31),(30,33),(32,35),(33,37),(35,39),(37,41),(38,43),(40,45),(42,47),(43,49),(45,51),(47,53),(48,55),(50,56),(52,58),(53,60),(55,62),(57,64),(58,66),(60,68),(62,70),(63,72),(65,74),(67,76),(68,78),(70,80),(72,82),(73,85),(75,87),(77,88),(78,90),(80,92),(82,93),(83,95),(85,96),(87,97),(88,98),(90,99),(92,100),(93,100),(95,100),(97,100),(98,100),(100,100)),
    "chemia": ((0,1),(2,1),(3,3),(5,6),(7,8),(8,11),(10,14),(12,16),(13,18),(15,21),(17,23),(18,25),(20,27),(22,29),(23,31),(25,33),(27,35),(28,37),(30,39),(32,41),(33,43),(35,45),(37,47),(38,49),(40,51),(42,53),(43,55),(45,57),(47,59),(48,60),(50,62),(52,64),(53,66),(55,68),(57,69),(58,71),(60,73),(62,75),(63,76),(65,78),(67,79),(68,80),(70,82),(72,83),(73,85),(75,86),(77,87),(78,89),(80,90),(82,91),(83,92),(85,94),(87,95),(88,96),(90,97),(92,97),(93,98),(95,99),(97,100),(98,100),(100,100)),
    "fizyka": ((0,1),(2,1),(3,1),(5,2),(7,4),(8,6),(10,9),(12,12),(13,14),(15,17),(17,19),(18,21),(20,23),(22,24),(23,26),(25,27),(27,29),(28,30),(30,32),(32,33),(33,34),(35,35),(37,37),(38,38),(40,39),(42,41),(43,42),(45,44),(47,45),(48,47),(50,48),(52,50),(53,51),(55,53),(57,54),(58,56),(60,57),(62,59),(63,61),(65,62),(67,64),(68,66),(70,67),(72,69),(73,71),(75,73),(77,75),(78,76),(80,78),(82,80),(83,82),(85,84),(87,86),(88,88),(90,90),(92,92),(93,94),(95,96),(97,97),(98,99),(100,100)),
}

DATA_2025 = {
    "matematyka": SubjectStats(
        subject="matematyka", year=2025, n=67_384,
        mean=33, median=28, sd=26, modal=0,
        stanine_upper=(0, 2, 8, 22, 38, 56, 76, 100, 100), centile=_CENT2025["matematyka"],
        source=f"{_RAPORT.format('matematyka')}; {_STAN}; {_CENT}"),
    "biologia": SubjectStats(
        subject="biologia", year=2025, n=41_718,
        mean=46, median=45, sd=24, modal=20,
        stanine_upper=(10, 15, 23, 35, 53, 67, 77, 85, 100), centile=_CENT2025["biologia"],
        source=f"{_RAPORT.format('biologia')}; {_STAN}; {_CENT}"),
    "chemia": SubjectStats(
        subject="chemia", year=2025, n=20_340,
        mean=43, median=40, sd=26, modal=8,
        stanine_upper=(5, 8, 17, 32, 48, 65, 80, 90, 100), centile=_CENT2025["chemia"],
        source=f"{_RAPORT.format('chemia')}; {_STAN}; {_CENT}"),
    "fizyka": SubjectStats(
        subject="fizyka", year=2025, n=13_961,
        mean=52, median=53, sd=29, modal=13,
        stanine_upper=(7, 12, 22, 42, 63, 80, 90, 97, 100), centile=_CENT2025["fizyka"],
        source=f"{_RAPORT.format('fizyka')}; {_STAN}; {_CENT}"),
}

TOTAL_GRADUATES_2025 = 255_517  # Sprawozdanie ogólne 2025


# ---------------------------------------------------------------------------
# Third-subject med-pool marginal (the "reference population" correction).
# ---------------------------------------------------------------------------
# The WUM third slot is matematyka R OR fizyka R. The *national* extended-level
# marginal for those subjects is the WRONG reference population for a med applicant:
# matematyka R (N≈88.9k, mean 37%) is dominated by NON-med candidates (engineering,
# economics, CS) who sit well to the LEFT of med-track students. A med applicant's
# maths is drawn from maths-R *conditioned on also taking biologia R and chemia R* —
# a right-shifted sub-population. Ranking a fixed score against the raw national pool
# overstates the candidate and understates the field on the third subject.
#
# THIRD_MEDPOOL_GAP is the estimated national -> med-pool MEAN uplift (percentage
# points) for each third-slot subject. It is applied as a max-entropy reweight of the
# national marginal (model.Marginal(tilt_shift=gap)), producing a DISTINCT med-pool
# marginal on the same [0,100] support — not the raw national one.
#
# Provenance / status: INTERIM ESTIMATE. The clean data-grounded route is to
# reconstruct the third-subject profile from published admitted-cohort subject scores
# (WUM and peers publish last-admitted subject scores and often admitted distributions);
# replace these gaps with that data when in hand. The interim values below are a
# selection-reweight proxy sized to the estimated national-vs-med-pool mean gap:
#   * matematyka: +13 pts (national ~37 -> med-pool ~50). Large, because national
#     maths-R is heavily diluted by strong-but-non-med technical candidates AND a long
#     weak tail; med-track co-takers of bio+chem cluster clearly above the all-comers mean.
#   * fizyka: +8 pts (national ~42 -> med-pool ~50). Smaller, because physics-R is
#     already more self-selected/able, so the med vs all-comers gap is narrower.
# Both are overridable per-year via the JSON loader ("medpool_gap": {...}) and via the
# app slider, and are deliberately conservative pending admitted-cohort data.
THIRD_MEDPOOL_GAP = {"matematyka": 13.0, "fizyka": 8.0}
THIRD_MEDPOOL_SOURCE = (
    "Interim med-pool reweight of the national third-subject marginal onto the "
    "med-applicant sub-population (co-takers of biologia R + chemia R). Gaps: "
    "matematyka +13, fizyka +8 pts of mean. REPLACE with published WUM/peer "
    "admitted-cohort subject profiles when available.")


def third_medpool_gap(subject: str, overrides: dict | None = None) -> float:
    """National -> med-pool mean uplift (pts) for a third-slot subject. 0 if unknown."""
    if overrides and subject in overrides:
        return float(overrides[subject])
    return float(THIRD_MEDPOOL_GAP.get(subject, 0.0))


@dataclass
class YearData:
    """All subjects for a given year, plus cohort metadata."""
    year: int
    subjects: dict          # subject key -> SubjectStats
    total_graduates: int | None = None
    note: str = ""
    medpool_gap: dict | None = None   # optional per-subject national->med-pool mean uplift

    def get(self, subject: str) -> SubjectStats:
        if subject not in self.subjects:
            raise KeyError(f"no {subject} data for {self.year}; have {list(self.subjects)}")
        return self.subjects[subject]

    def medpool_gap_for(self, subject: str) -> float:
        """The national->med-pool mean uplift (pts) for a third-slot subject this year."""
        return third_medpool_gap(subject, self.medpool_gap)


def load_2025() -> YearData:
    """The built-in, sourced official dataset."""
    return YearData(year=2025, subjects=dict(DATA_2025),
                    total_graduates=TOTAL_GRADUATES_2025,
                    note="Official CKE/OKE 2025 extended-level results.")


def load_year(path: str | Path) -> YearData:
    """Load / override a year from JSON.

    Enables ingesting 2026 (or corrected 2025) data once published, with no code
    change. JSON shape:
        {"year": 2026, "total_graduates": 332000, "note": "...",
         "subjects": {"chemia": {"n":..., "mean":..., "median":..., "sd":...,
                                  "modal":..., "stanine_upper":[...], "source":"..."}, ...}}
    Missing per-subject fields fall back to the 2025 built-in for that subject.
    """
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    year = int(blob["year"])
    subs = {}
    for key, s in blob.get("subjects", {}).items():
        base = DATA_2025.get(key)
        cent = s.get("centile")
        cent = tuple(tuple(pair) for pair in cent) if cent else (base.centile if base else ())
        subs[key] = SubjectStats(
            subject=key, year=year,
            n=int(s.get("n", base.n if base else 0)),
            mean=float(s.get("mean", base.mean if base else 0)),
            median=float(s.get("median", base.median if base else 0)),
            sd=float(s.get("sd", base.sd if base else 0)),
            modal=float(s.get("modal", base.modal if base else 0)),
            stanine_upper=tuple(s.get("stanine_upper",
                                      base.stanine_upper if base else (0,)*9)),
            centile=cent,
            source=s.get("source", "user-provided"))
    return YearData(year=year, subjects=subs,
                    total_graduates=blob.get("total_graduates"),
                    note=blob.get("note", "user-provided"),
                    medpool_gap=blob.get("medpool_gap"))


def dump_template(path: str | Path, year: int = 2026) -> Path:
    """Write an editable JSON template pre-filled with the 2025 numbers."""
    p = Path(path)
    blob = {"year": year, "total_graduates": None,
            "note": f"Edit with official {year} figures when published.",
            "subjects": {k: {kk: vv for kk, vv in asdict(v).items()
                             if kk not in ("subject", "year")}
                         for k, v in DATA_2025.items()}}
    p.write_text(json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
