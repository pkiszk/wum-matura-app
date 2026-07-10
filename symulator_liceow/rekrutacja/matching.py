"""Silnik przydziału: student-proposing deferred acceptance (Gale-Shapley).

Zwraca pełny, "dydaktyczny" log zdarzeń per runda: kto się gdzie zgłosił, kto
został zakwalifikowany tymczasowo, kto został wypchnięty, przez kogo i dokąd
spadł. Log pozwala krok po kroku zwizualizować powstawanie przydziału i
progów punktowych.

Interfejs jest przygotowany tak, aby dało się dołożyć "rundę uzupełniającą"
(wolne miejsca po niepotwierdzeniu woli) bez przebudowy — patrz
``przydziel(...)`` przyjmujące zbiór zablokowanych/zajętych miejsc.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .modele import Kandydat, Oddzial, WynikPrzydzialu
from .punktacja import punkty


# ---------------------------------------------------------------------------
# Struktury logu
# ---------------------------------------------------------------------------


@dataclass
class ZdarzenieWypchniecia:
    """Kandydat wypchnięty z oddziału w danej rundzie."""

    kandydat_id: int
    z_oddzialu: int
    przez_kogo: Optional[int]  # id kandydata, który zajął miejsce (marginalny nowy)
    spadl_do_oddzialu: Optional[int]  # dokąd trafił w tej samej rundzie (None = wolny)
    niezakwalifikowany: bool  # True jeśli wyczerpał listę preferencji


@dataclass
class ZdarzenieZgloszenia:
    """Kandydat zgłasza się (proponuje) do oddziału ze swojej listy."""

    kandydat_id: int
    do_oddzialu: int
    numer_preferencji: int  # 0 = 1. wybór


@dataclass
class RundaLog:
    numer: int
    zgloszenia: list[ZdarzenieZgloszenia] = field(default_factory=list)
    wypchniecia: list[ZdarzenieWypchniecia] = field(default_factory=list)
    # Migawka przydziału po rundzie: kandydat_id -> oddzial_id (lub None).
    przydzial: dict[int, Optional[int]] = field(default_factory=dict)
    # Numer preferencji, na której siedzi każdy zakwalifikowany: kandydat_id -> nr.
    numer_preferencji: dict[int, int] = field(default_factory=dict)
    # Progi punktowe po rundzie: oddzial_id -> próg (punkty ostatniego
    # zakwalifikowanego wg rankingu punktowego) albo None gdy niedobór chętnych.
    progi: dict[int, Optional[float]] = field(default_factory=dict)

    @property
    def liczba_zakwalifikowanych(self) -> int:
        return sum(1 for o in self.przydzial.values() if o is not None)

    @property
    def liczba_wypchnietych(self) -> int:
        return len(self.wypchniecia)


@dataclass
class WynikSymulacji:
    """Wynik pełnej symulacji deferred acceptance."""

    rundy: list[RundaLog]
    przydzial: list[WynikPrzydzialu]  # ostateczny
    progi_koncowe: dict[int, Optional[float]]

    @property
    def liczba_rund(self) -> int:
        return len(self.rundy)

    def przydzial_kandydata(self, kandydat_id: int) -> WynikPrzydzialu:
        for w in self.przydzial:
            if w.kandydat_id == kandydat_id:
                return w
        raise KeyError(kandydat_id)


# ---------------------------------------------------------------------------
# Ranking w oddziale
# ---------------------------------------------------------------------------


def klucz_rankingowy(
    kandydat: Kandydat, oddzial: Oddzial, los: float
) -> tuple:
    """Klucz sortowania kandydatów w oddziale (rosnąco = od najlepszego).

    Kolejność:
      1. olimpijczycy (laureaci/finaliści) — przed rankingiem punktowym,
      2. punkty malejąco,
      3. problemy zdrowotne kandydata (kryterium a),
      4. suma kryteriów ex aequo malejąco (kryterium b),
      5. losowo z seedem (kryterium c) — pełny remis.
    """
    return (
        0 if kandydat.olimpijczyk else 1,
        -punkty(kandydat, oddzial),
        0 if kandydat.problemy_zdrowotne else 1,
        -kandydat.kryteria_ex_aequo,
        los,
    )


def ranking_oddzialu(
    kandydaci: list[Kandydat],
    oddzial: Oddzial,
    losy: dict[int, float],
) -> list[Kandydat]:
    """Zwraca kandydatów posortowanych od najlepszego wg reguł tie-break."""
    return sorted(
        kandydaci,
        key=lambda k: klucz_rankingowy(k, oddzial, losy[k.id]),
    )


# ---------------------------------------------------------------------------
# Silnik deferred acceptance
# ---------------------------------------------------------------------------


def _losy_kandydatow(kandydaci: list[Kandydat], seed: int) -> dict[int, float]:
    """Deterministyczny losowy tie-break per kandydat (seed → powtarzalność)."""
    rng = random.Random(seed)
    # Sortujemy po id, aby kolejność losowania nie zależała od kolejności wejścia.
    losy: dict[int, float] = {}
    for k in sorted(kandydaci, key=lambda k: k.id):
        losy[k.id] = rng.random()
    return losy


def _prog_oddzialu(
    zakwalifikowani: list[Kandydat],
    oddzial: Oddzial,
) -> Optional[float]:
    """Próg = punkty ostatniego zakwalifikowanego wg rankingu punktowego.

    Olimpijczycy (poza limitem) nie wyznaczają progu. Gdy chętnych (poza
    olimpijczykami) jest nie więcej niż miejsc — brak progu (None).
    """
    punktowani = [k for k in zakwalifikowani if not k.olimpijczyk]
    if len(punktowani) < oddzial.limit_miejsc or not punktowani:
        return None
    return min(punkty(k, oddzial) for k in punktowani)


def przydziel(
    kandydaci: list[Kandydat],
    oddzialy: list[Oddzial],
    seed: int = 0,
    zajete_miejsca: Optional[dict[int, int]] = None,
) -> WynikSymulacji:
    """Uruchamia deferred acceptance i zwraca pełny log rund.

    Parametry
    ---------
    zajete_miejsca:
        Opcjonalna redukcja limitów miejsc oddziałów (oddzial_id -> liczba
        miejsc już zajętych). Przygotowane pod przyszłą "rundę uzupełniającą"
        po potwierdzaniu woli — silnik nie wymaga wtedy przebudowy.
    """
    oddzialy_wg_id: dict[int, Oddzial] = {o.id: o for o in oddzialy}
    kandydaci_wg_id: dict[int, Kandydat] = {k.id: k for k in kandydaci}
    losy = _losy_kandydatow(kandydaci, seed)
    zajete = zajete_miejsca or {}

    def limit(o: Oddzial) -> int:
        return max(0, o.limit_miejsc - zajete.get(o.id, 0))

    # next_pref[c] = indeks kolejnej preferencji do zgłoszenia.
    next_pref: dict[int, int] = {k.id: 0 for k in kandydaci}
    # przydzial[c] = oddzial_id (tymczasowo) lub None.
    przydzial: dict[int, Optional[int]] = {k.id: None for k in kandydaci}
    # held[o] = zbiór id kandydatów trzymanych tymczasowo w oddziale o.
    held: dict[int, set[int]] = {o.id: set() for o in oddzialy}

    rundy: list[RundaLog] = []
    numer_rundy = 0

    while True:
        numer_rundy += 1
        runda = RundaLog(numer=numer_rundy)

        # 1) Wolni kandydaci z pozostałymi preferencjami zgłaszają się do
        #    kolejnego oddziału na liście.
        nowe_zgloszenia: dict[int, list[int]] = {}  # oddzial_id -> [kandydat_id]
        for k in kandydaci:
            if przydzial[k.id] is not None:
                continue
            idx = next_pref[k.id]
            if idx >= len(k.preferencje):
                continue  # wyczerpał listę — niezakwalifikowany
            oddzial_id = k.preferencje[idx]
            next_pref[k.id] = idx + 1
            nowe_zgloszenia.setdefault(oddzial_id, []).append(k.id)
            runda.zgloszenia.append(
                ZdarzenieZgloszenia(
                    kandydat_id=k.id, do_oddzialu=oddzial_id, numer_preferencji=idx
                )
            )

        if not nowe_zgloszenia:
            break  # punkt stały — nikt się już nie zgłasza

        # 2) Każdy oddział, który dostał nowe zgłoszenia, re-ewaluuje pulę.
        for oddzial_id, nowi in nowe_zgloszenia.items():
            oddzial = oddzialy_wg_id[oddzial_id]
            incumbenci = set(held[oddzial_id])
            pula_ids = incumbenci | set(nowi)
            pula = [kandydaci_wg_id[c] for c in pula_ids]

            olimpijczycy = [k for k in pula if k.olimpijczyk]
            reszta = [k for k in pula if not k.olimpijczyk]
            reszta_ranking = ranking_oddzialu(reszta, oddzial, losy)

            przyjeci_reszta = reszta_ranking[: limit(oddzial)]
            odrzuceni = reszta_ranking[limit(oddzial):]
            przyjeci_ids = {k.id for k in olimpijczycy} | {k.id for k in przyjeci_reszta}

            # Marginalny nowy przyjęty (najniżej w rankingu przyjęty, który jest
            # nowym zgłoszeniem) — "przez kogo" wypchnięto incumbenta.
            nowi_przyjeci = [k for k in przyjeci_reszta if k.id in set(nowi)]
            marginalny = nowi_przyjeci[-1].id if nowi_przyjeci else None

            held[oddzial_id] = przyjeci_ids
            for k in odrzuceni:
                if k.id in incumbenci:
                    # Incumbent wypchnięty przez nowych.
                    runda.wypchniecia.append(
                        ZdarzenieWypchniecia(
                            kandydat_id=k.id,
                            z_oddzialu=oddzial_id,
                            przez_kogo=marginalny,
                            spadl_do_oddzialu=None,  # uzupełnimy po rundzie
                            niezakwalifikowany=False,
                        )
                    )
                # Nowy odrzucony od razu — traktujemy jak zgłoszenie bez skutku
                # (nie logujemy jako "wypchnięcie", bo nigdy nie siedział).
                przydzial[k.id] = None

            for c in przyjeci_ids:
                przydzial[c] = oddzial_id

        # 3) Migawka i progi po rundzie.
        for k in kandydaci:
            runda.przydzial[k.id] = przydzial[k.id]
            if przydzial[k.id] is not None:
                # numer preferencji = pozycja przydzielonego oddziału na liście
                runda.numer_preferencji[k.id] = k.preferencje.index(przydzial[k.id])
        for o in oddzialy:
            zakw = [kandydaci_wg_id[c] for c in held[o.id]]
            runda.progi[o.id] = _prog_oddzialu(zakw, o)

        # 4) Dokąd spadli wypchnięci: jeśli w tej samej rundzie zdążyli już
        #    trafić gdzie indziej (rzadkie w modelu round-based) — zwykle spadną
        #    w kolejnej rundzie, więc zostawiamy None = "wolny, spada dalej".
        for w in runda.wypchniecia:
            docel = przydzial[w.kandydat_id]
            if docel is not None:
                w.spadl_do_oddzialu = docel
            elif next_pref[w.kandydat_id] >= len(
                kandydaci_wg_id[w.kandydat_id].preferencje
            ):
                w.niezakwalifikowany = True

        rundy.append(runda)

        # Zabezpieczenie przed nieskończoną pętlą.
        if numer_rundy > len(kandydaci) * len(oddzialy) + 10:
            break

    # Ostateczny przydział.
    wyniki: list[WynikPrzydzialu] = []
    for k in kandydaci:
        oid = przydzial[k.id]
        if oid is None:
            wyniki.append(WynikPrzydzialu(k.id, None, None, None))
        else:
            nr = k.preferencje.index(oid)
            wyniki.append(
                WynikPrzydzialu(k.id, oid, nr, round(punkty(k, oddzialy_wg_id[oid]), 2))
            )

    progi_koncowe: dict[int, Optional[float]] = {}
    for o in oddzialy:
        zakw = [kandydaci_wg_id[c] for c in held[o.id]]
        progi_koncowe[o.id] = _prog_oddzialu(zakw, o)

    return WynikSymulacji(rundy=rundy, przydzial=wyniki, progi_koncowe=progi_koncowe)


# ---------------------------------------------------------------------------
# Tryb naiwny (dla porównania dydaktycznego)
# ---------------------------------------------------------------------------


def przydziel_naiwnie(
    kandydaci: list[Kandydat],
    oddzialy: list[Oddzial],
    seed: int = 0,
) -> list[WynikPrzydzialu]:
    """Naiwny pojedynczy przebieg BEZ wypychania (mechanizm typu "bostoński").

    Preferencje przetwarzane poziomami: najpierw wszystkie 1. wybory (oddziały
    zapełniają się z najlepszych chętnych), potem 2. wybory tylko do miejsc,
    które zostały wolne, itd. Miejsce raz zajęte jest zablokowane — brak
    kaskadowego wypychania. Skutek: kandydaci z wyższymi punktami bywają
    odrzuceni na rzecz słabszych, którzy postawili dany oddział wyżej.
    """
    oddzialy_wg_id = {o.id: o for o in oddzialy}
    kandydaci_wg_id = {k.id: k for k in kandydaci}
    losy = _losy_kandydatow(kandydaci, seed)

    przydzial: dict[int, Optional[int]] = {k.id: None for k in kandydaci}
    wolne: dict[int, int] = {o.id: o.limit_miejsc for o in oddzialy}

    max_pref = max((len(k.preferencje) for k in kandydaci), default=0)
    for poziom in range(max_pref):
        # Zbierz zgłoszenia tego poziomu od jeszcze nieprzydzielonych.
        zgloszenia: dict[int, list[int]] = {}
        for k in kandydaci:
            if przydzial[k.id] is not None:
                continue
            if poziom < len(k.preferencje):
                zgloszenia.setdefault(k.preferencje[poziom], []).append(k.id)
        # Każdy oddział przyjmuje najlepszych do wyczerpania WOLNYCH miejsc.
        for oddzial_id, chetni in zgloszenia.items():
            oddzial = oddzialy_wg_id[oddzial_id]
            ranking = ranking_oddzialu(
                [kandydaci_wg_id[c] for c in chetni], oddzial, losy
            )
            for k in ranking[: wolne[oddzial_id]]:
                przydzial[k.id] = oddzial_id
            wolne[oddzial_id] = max(0, wolne[oddzial_id] - len(chetni))

    wyniki: list[WynikPrzydzialu] = []
    for k in kandydaci:
        oid = przydzial[k.id]
        if oid is None:
            wyniki.append(WynikPrzydzialu(k.id, None, None, None))
        else:
            nr = k.preferencje.index(oid)
            wyniki.append(
                WynikPrzydzialu(k.id, oid, nr, round(punkty(k, oddzialy_wg_id[oid]), 2))
            )
    return wyniki


# ---------------------------------------------------------------------------
# Weryfikacja stabilności (używana w testach i w UI)
# ---------------------------------------------------------------------------


@dataclass
class ParaBlokujaca:
    kandydat_id: int
    oddzial_id: int
    punkty_kandydata: float
    prog_oddzialu: Optional[float]


def progi_z_przydzialu(
    przydzial: list[WynikPrzydzialu],
    kandydaci: list[Kandydat],
    oddzialy: list[Oddzial],
) -> dict[int, Optional[float]]:
    """Odtwarza progi (punkty ostatniego przyjętego) z gotowego przydziału."""
    kandydaci_wg_id = {k.id: k for k in kandydaci}
    oddzialy_wg_id = {o.id: o for o in oddzialy}
    przyjeci: dict[int, list[Kandydat]] = {o.id: [] for o in oddzialy}
    for w in przydzial:
        if w.oddzial_id is not None:
            przyjeci[w.oddzial_id].append(kandydaci_wg_id[w.kandydat_id])
    return {
        o.id: _prog_oddzialu(przyjeci[o.id], oddzialy_wg_id[o.id]) for o in oddzialy
    }


def znajdz_pary_blokujace(
    przydzial: list[WynikPrzydzialu],
    kandydaci: list[Kandydat],
    oddzialy: list[Oddzial],
) -> list[ParaBlokujaca]:
    """Zwraca pary blokujące — dowód niestabilności przydziału.

    Para (kandydat, oddział) blokuje, gdy kandydat woli ten oddział od swojego
    przydziału (lub jest nigdzie nieprzydzielony) ORAZ miałby w nim więcej
    punktów niż ostatni zakwalifikowany (albo oddział ma wolne miejsca).
    """
    kandydaci_wg_id = {k.id: k for k in kandydaci}
    oddzialy_wg_id = {o.id: o for o in oddzialy}
    progi = progi_z_przydzialu(przydzial, kandydaci, oddzialy)
    liczba_przyjetych: dict[int, int] = {o.id: 0 for o in oddzialy}
    for w in przydzial:
        if w.oddzial_id is not None:
            liczba_przyjetych[w.oddzial_id] += 1

    pary: list[ParaBlokujaca] = []
    for w in przydzial:
        k = kandydaci_wg_id[w.kandydat_id]
        obecny_nr = w.numer_preferencji if w.numer_preferencji is not None else len(k.preferencje)
        # Preferencje lepsze od obecnego przydziału.
        for nr, oddzial_id in enumerate(k.preferencje[:obecny_nr]):
            oddzial = oddzialy_wg_id[oddzial_id]
            pkt = punkty(k, oddzial)
            prog = progi[oddzial_id]
            ma_wolne = liczba_przyjetych[oddzial_id] < oddzial.limit_miejsc
            if ma_wolne or (prog is not None and pkt > prog):
                pary.append(
                    ParaBlokujaca(
                        kandydat_id=k.id,
                        oddzial_id=oddzial_id,
                        punkty_kandydata=round(pkt, 2),
                        prog_oddzialu=prog,
                    )
                )
    return pary
