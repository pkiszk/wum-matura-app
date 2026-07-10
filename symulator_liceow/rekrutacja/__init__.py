"""Rdzeń domenowy symulatora rekrutacji do liceów.

Czysty Python, bez zależności od warstwy UI (Streamlit/Plotly). Zawiera model
danych, punktację, silnik przydziału (deferred acceptance) i generator danych.
"""

from .modele import (
    Kandydat,
    Oddzial,
    Szkola,
    WynikiEgzaminu,
    WynikPrzydzialu,
    NAZWY_PRZEDMIOTOW,
    UNIWERSUM_PRZEDMIOTOW,
)
from .punktacja import (
    punkty,
    punkty_egzamin,
    punkty_oceny,
    punkty_dodatkowe,
    rozbicie_punktow,
    PRZELICZNIK_OCEN,
    MAX_PUNKTY,
)
from .matching import (
    przydziel,
    przydziel_naiwnie,
    znajdz_pary_blokujace,
    progi_z_przydzialu,
    WynikSymulacji,
    RundaLog,
    ParaBlokujaca,
)
from .generator import (
    generuj_miasto,
    Miasto,
    ParametrySymulacji,
    PROFILE,
)
from .analiza import (
    podsumowanie_przydzialu,
    Podsumowanie,
    kandydaci_na_miejsce,
)

__all__ = [
    "Kandydat",
    "Oddzial",
    "Szkola",
    "WynikiEgzaminu",
    "WynikPrzydzialu",
    "NAZWY_PRZEDMIOTOW",
    "UNIWERSUM_PRZEDMIOTOW",
    "punkty",
    "punkty_egzamin",
    "punkty_oceny",
    "punkty_dodatkowe",
    "rozbicie_punktow",
    "PRZELICZNIK_OCEN",
    "MAX_PUNKTY",
    "przydziel",
    "przydziel_naiwnie",
    "znajdz_pary_blokujace",
    "progi_z_przydzialu",
    "WynikSymulacji",
    "RundaLog",
    "ParaBlokujaca",
    "generuj_miasto",
    "Miasto",
    "ParametrySymulacji",
    "PROFILE",
    "podsumowanie_przydzialu",
    "Podsumowanie",
    "kandydaci_na_miejsce",
]
