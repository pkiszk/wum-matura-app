"""CKE 2025 matura data — the empirical foundation for the percentile module.

This module is *unrelated* to the DCF / screening pipeline. It holds the official,
sourced 2025 extended-level ("poziom rozszerzony") result statistics for the four
subjects relevant to Warsaw Medical University (WUM) recruitment, and a loader that
lets you override / add years (e.g. 2026) from a JSON file without touching code.

Why these numbers and not a live scrape:
    CKE does NOT publish a machine-readable percent-by-percent histogram. What it
    *does* publish, per subject, is (a) distribution parameters (mean/median/SD/N)
    and (b) the "skala staninowa" — a 9-band table mapping score ranges to fixed
    population fractions (4/7/12/17/20/17/12/7/4 %). Those bands ARE published
    percentile boundaries, so we treat the stanine table as the primary empirical
    object: it reconstructs each subject's real (skewed) score->percentile curve
    directly from official data. Every figure below carries its source URL.

Sources (all official CKE / OKE, 2025 exam):
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
    stanine_upper: tuple  # 9 upper-score boundaries, %
    source: str = ""      # provenance note

    def cdf_knots(self):
        """Return (scores, cum) monotone knots for the empirical CDF, anchored at (0,0)."""
        cum = []
        acc = 0.0
        for b in STANINE_BANDS:
            acc += b
            cum.append(round(acc, 4))
        # anchor a (0,0) point so scores below the first stanine top interpolate sanely
        scores = [0.0] + list(self.stanine_upper)
        cumc = [0.0] + cum
        # de-duplicate any repeated boundary (e.g. matematyka's merged 100,100)
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

DATA_2025 = {
    "matematyka": SubjectStats(
        subject="matematyka", year=2025, n=67_384,
        mean=33, median=28, sd=26, modal=0,
        stanine_upper=(0, 2, 8, 22, 38, 56, 76, 100, 100),
        source=f"{_RAPORT.format('matematyka')}; {_STAN}"),
    "biologia": SubjectStats(
        subject="biologia", year=2025, n=41_718,
        mean=46, median=45, sd=24, modal=20,
        stanine_upper=(10, 15, 23, 35, 53, 67, 77, 85, 100),
        source=f"{_RAPORT.format('biologia')}; {_STAN}"),
    "chemia": SubjectStats(
        subject="chemia", year=2025, n=20_340,
        mean=43, median=40, sd=26, modal=8,
        stanine_upper=(5, 8, 17, 32, 48, 65, 80, 90, 100),
        source=f"{_RAPORT.format('chemia')}; {_STAN}"),
    "fizyka": SubjectStats(
        subject="fizyka", year=2025, n=13_961,
        mean=52, median=53, sd=29, modal=13,
        stanine_upper=(7, 12, 22, 42, 63, 80, 90, 97, 100),
        source=f"{_RAPORT.format('fizyka')}; {_STAN}"),
}

TOTAL_GRADUATES_2025 = 255_517  # Sprawozdanie ogólne 2025


@dataclass
class YearData:
    """All subjects for a given year, plus cohort metadata."""
    year: int
    subjects: dict          # subject key -> SubjectStats
    total_graduates: int | None = None
    note: str = ""

    def get(self, subject: str) -> SubjectStats:
        if subject not in self.subjects:
            raise KeyError(f"no {subject} data for {self.year}; have {list(self.subjects)}")
        return self.subjects[subject]


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
        subs[key] = SubjectStats(
            subject=key, year=year,
            n=int(s.get("n", base.n if base else 0)),
            mean=float(s.get("mean", base.mean if base else 0)),
            median=float(s.get("median", base.median if base else 0)),
            sd=float(s.get("sd", base.sd if base else 0)),
            modal=float(s.get("modal", base.modal if base else 0)),
            stanine_upper=tuple(s.get("stanine_upper",
                                      base.stanine_upper if base else (0,)*9)),
            source=s.get("source", "user-provided"))
    return YearData(year=year, subjects=subs,
                    total_graduates=blob.get("total_graduates"),
                    note=blob.get("note", "user-provided"))


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
