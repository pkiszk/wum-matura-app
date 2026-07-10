"""Analiza wyników — metryki podsumowujące dla warstwy prezentacji."""

from __future__ import annotations

from dataclasses import dataclass, field

from .modele import Kandydat, Oddzial, WynikPrzydzialu


@dataclass
class Podsumowanie:
    """Zbiorcze metryki przydziału."""

    liczba_kandydatow: int
    zakwalifikowani: int
    niezakwalifikowani: int
    # rozklad[i] = liczba kandydatów zakwalifikowanych do i-tej preferencji (0 = 1. wybór)
    rozklad_preferencji: dict[int, int] = field(default_factory=dict)

    @property
    def odsetek_1_preferencja(self) -> float:
        if not self.zakwalifikowani and not self.niezakwalifikowani:
            return 0.0
        return 100.0 * self.rozklad_preferencji.get(0, 0) / self.liczba_kandydatow

    def odsetek_preferencji(self, nr: int) -> float:
        return 100.0 * self.rozklad_preferencji.get(nr, 0) / max(1, self.liczba_kandydatow)

    @property
    def odsetek_niezakwalifikowani(self) -> float:
        return 100.0 * self.niezakwalifikowani / max(1, self.liczba_kandydatow)


def podsumowanie_przydzialu(przydzial: list[WynikPrzydzialu]) -> Podsumowanie:
    """Liczy metryki: ilu w której preferencji, ilu bez miejsca."""
    rozklad: dict[int, int] = {}
    zakw = 0
    niezakw = 0
    for w in przydzial:
        if w.oddzial_id is None:
            niezakw += 1
        else:
            zakw += 1
            nr = w.numer_preferencji or 0
            rozklad[nr] = rozklad.get(nr, 0) + 1
    return Podsumowanie(
        liczba_kandydatow=len(przydzial),
        zakwalifikowani=zakw,
        niezakwalifikowani=niezakw,
        rozklad_preferencji=rozklad,
    )


def kandydaci_na_miejsce(
    kandydaci: list[Kandydat],
    oddzialy: list[Oddzial],
) -> dict[int, float]:
    """Popularność oddziału: liczba kandydatów, którzy go wskazali / limit miejsc.

    Liczymy każdego kandydata, który ma dany oddział gdziekolwiek na liście
    preferencji (miara "oblegania").
    """
    liczba: dict[int, int] = {o.id: 0 for o in oddzialy}
    for k in kandydaci:
        for oid in k.preferencje:
            if oid in liczba:
                liczba[oid] += 1
    wynik: dict[int, float] = {}
    for o in oddzialy:
        wynik[o.id] = liczba[o.id] / o.limit_miejsc if o.limit_miejsc else 0.0
    return wynik
