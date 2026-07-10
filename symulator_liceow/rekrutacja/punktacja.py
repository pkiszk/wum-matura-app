"""Punktacja rekrutacyjna — maksymalnie 200 pkt.

Punkty liczone są ODDZIELNIE dla każdej pary (kandydat, oddział), ponieważ
oddziały różnią się przedmiotami punktowanymi. To fundament modelu danych.
"""

from __future__ import annotations

from dataclasses import dataclass

from .modele import Kandydat, Oddzial

# Przelicznik ocen ze świadectwa na punkty (max 18 za przedmiot).
# celujący(6)=18, bardzo dobry(5)=17, dobry(4)=14, dostateczny(3)=8, dopuszczający(2)=2
PRZELICZNIK_OCEN: dict[int, int] = {6: 18, 5: 17, 4: 14, 3: 8, 2: 2}

# Wagi egzaminu ósmoklasisty (max 100 pkt łącznie).
WAGA_POLSKI = 0.35
WAGA_MATEMATYKA = 0.35
WAGA_JEZYK_OBCY = 0.30

# Punkty dodatkowe.
PUNKTY_ZA_WYROZNIENIE = 7
PUNKTY_ZA_WOLONTARIAT = 3
MAX_PUNKTY_ZA_KONKURSY = 18

MAX_PUNKTY = 200.0


@dataclass
class RozbiciePunktow:
    """Rozbicie punktów kandydata w danym oddziale — do prezentacji w UI."""

    egzamin: float
    oceny: float
    wyroznienie: float
    wolontariat: float
    konkursy: float
    # Szczegół ocen: przedmiot -> (ocena, punkty).
    oceny_szczegoly: dict[str, tuple[int, int]]

    @property
    def dodatkowe(self) -> float:
        return self.wyroznienie + self.wolontariat + self.konkursy

    @property
    def suma(self) -> float:
        return self.egzamin + self.oceny + self.dodatkowe


def punkty_egzamin(kandydat: Kandydat) -> float:
    """Punkty za egzamin ósmoklasisty (max 100)."""
    e = kandydat.egzamin
    return (
        e.polski * WAGA_POLSKI
        + e.matematyka * WAGA_MATEMATYKA
        + e.jezyk_obcy * WAGA_JEZYK_OBCY
    )


def punkty_oceny(kandydat: Kandydat, oddzial: Oddzial) -> float:
    """Punkty za oceny z 4 przedmiotów punktowanych oddziału (max 72)."""
    total = 0
    for przedmiot in oddzial.wszystkie_przedmioty_punktowane:
        ocena = kandydat.oceny[przedmiot]
        total += PRZELICZNIK_OCEN[ocena]
    return float(total)


def punkty_dodatkowe(kandydat: Kandydat) -> float:
    """Świadectwo z wyróżnieniem, wolontariat, konkursy (max 28)."""
    p = 0.0
    if kandydat.swiadectwo_z_wyroznieniem:
        p += PUNKTY_ZA_WYROZNIENIE
    if kandydat.wolontariat:
        p += PUNKTY_ZA_WOLONTARIAT
    p += min(kandydat.punkty_za_konkursy, MAX_PUNKTY_ZA_KONKURSY)
    return p


def punkty(kandydat: Kandydat, oddzial: Oddzial) -> float:
    """Łączna liczba punktów kandydata w danym oddziale (max 200)."""
    return (
        punkty_egzamin(kandydat)
        + punkty_oceny(kandydat, oddzial)
        + punkty_dodatkowe(kandydat)
    )


def rozbicie_punktow(kandydat: Kandydat, oddzial: Oddzial) -> RozbiciePunktow:
    """Pełne rozbicie punktów — do karty kandydata w UI."""
    szczegoly: dict[str, tuple[int, int]] = {}
    for przedmiot in oddzial.wszystkie_przedmioty_punktowane:
        ocena = kandydat.oceny[przedmiot]
        szczegoly[przedmiot] = (ocena, PRZELICZNIK_OCEN[ocena])
    return RozbiciePunktow(
        egzamin=round(punkty_egzamin(kandydat), 2),
        oceny=punkty_oceny(kandydat, oddzial),
        wyroznienie=float(PUNKTY_ZA_WYROZNIENIE if kandydat.swiadectwo_z_wyroznieniem else 0),
        wolontariat=float(PUNKTY_ZA_WOLONTARIAT if kandydat.wolontariat else 0),
        konkursy=float(min(kandydat.punkty_za_konkursy, MAX_PUNKTY_ZA_KONKURSY)),
        oceny_szczegoly=szczegoly,
    )
