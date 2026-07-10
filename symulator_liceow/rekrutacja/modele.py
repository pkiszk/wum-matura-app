"""Model domenowy symulatora rekrutacji do liceów.

Czysty Python — brak zależności od Streamlit, Plotly czy pandas. Wszystkie
struktury opisują dziedzinę rekrutacji do szkół ponadpodstawowych zgodnie z
polskimi przepisami (rozporządzenie MEN 2025, ustawa Prawo oświatowe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Przedmioty, dla których każdy kandydat ma ocenę na świadectwie. Polski i
# matematyka są punktowane ZAWSZE; pozostałe bywają "przedmiotami punktowanymi"
# zależnie od profilu oddziału.
UNIWERSUM_PRZEDMIOTOW: tuple[str, ...] = (
    "polski",
    "matematyka",
    "jezyk_obcy",
    "fizyka",
    "chemia",
    "biologia",
    "geografia",
    "historia",
    "informatyka",
    "wos",
    "angielski",
)

# Ludzkie etykiety przedmiotów do wyświetlania w UI.
NAZWY_PRZEDMIOTOW: dict[str, str] = {
    "polski": "język polski",
    "matematyka": "matematyka",
    "jezyk_obcy": "język obcy",
    "fizyka": "fizyka",
    "chemia": "chemia",
    "biologia": "biologia",
    "geografia": "geografia",
    "historia": "historia",
    "informatyka": "informatyka",
    "wos": "WOS",
    "angielski": "j. angielski (dodatkowy)",
}


@dataclass
class WynikiEgzaminu:
    """Wyniki egzaminu ósmoklasisty w procentach (0–100)."""

    polski: float
    matematyka: float
    jezyk_obcy: float


@dataclass
class Kandydat:
    """Pojedynczy kandydat do szkoły ponadpodstawowej.

    Uwaga: punkty kandydata NIE są przechowywane tutaj, bo zależą od oddziału
    (różne oddziały mają różne przedmioty punktowane). Liczy je funkcja
    ``rekrutacja.punktacja.punkty(kandydat, oddzial)``.
    """

    id: int
    imie: str
    egzamin: WynikiEgzaminu
    # Oceny 2–6 dla każdego przedmiotu z UNIWERSUM_PRZEDMIOTOW.
    oceny: dict[str, int]
    swiadectwo_z_wyroznieniem: bool = False
    wolontariat: bool = False
    punkty_za_konkursy: int = 0  # 0–18
    laureat_olimpiady: bool = False
    finalista_olimpiady: bool = False
    # Tie-break: "problemy zdrowotne ograniczające wybór" (kryterium a).
    problemy_zdrowotne: bool = False
    # Kryteria ex aequo (kryterium b) — liczba spełnionych z listy:
    # wielodzietność, niepełnosprawność kandydata / jednego rodzica / obojga
    # rodziców / rodzeństwa, samotne wychowywanie, piecza zastępcza.
    kryteria_ex_aequo: int = 0
    # Uporządkowana lista preferencji: identyfikatory oddziałów.
    preferencje: list[int] = field(default_factory=list)
    # Ukryta "siła" kandydata — używana wyłącznie przez generator i analizy,
    # nie wpływa bezpośrednio na punktację.
    sila: float = 0.0

    @property
    def olimpijczyk(self) -> bool:
        """Laureat lub finalista olimpiady przedmiotowej."""
        return self.laureat_olimpiady or self.finalista_olimpiady


@dataclass
class Oddzial:
    """Oddział = profil klasy w konkretnej szkole.

    Jednostka rekrutacji. Ma własny limit miejsc i własną parę przedmiotów
    punktowanych (poza polskim i matematyką, które liczą się zawsze).
    """

    id: int
    szkola_id: int
    nazwa_profilu: str
    # Dwa dodatkowe przedmioty punktowane (poza polskim i matematyką).
    przedmioty_punktowane: tuple[str, str]
    limit_miejsc: int

    @property
    def wszystkie_przedmioty_punktowane(self) -> tuple[str, str, str, str]:
        """Cztery przedmioty ze świadectwa liczone do punktów tego oddziału."""
        return ("polski", "matematyka", *self.przedmioty_punktowane)


@dataclass
class Szkola:
    """Szkoła ponadpodstawowa. Grupuje oddziały."""

    id: int
    nazwa: str
    prestiz: float  # względny prestiż (wpływa na model preferencji)
    oddzialy: list[int] = field(default_factory=list)  # identyfikatory oddziałów


@dataclass
class WynikPrzydzialu:
    """Ostateczny przydział jednego kandydata."""

    kandydat_id: int
    oddzial_id: Optional[int]  # None = niezakwalifikowany nigdzie
    # Na której pozycji własnej listy preferencji (0 = 1. wybór); None jeśli nigdzie.
    numer_preferencji: Optional[int]
    punkty: Optional[float]  # punkty w przydzielonym oddziale
