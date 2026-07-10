"""Testy własnościowe rdzenia rekrutacji.

Uruchom z katalogu ``symulator_liceow``:  pytest
"""

from __future__ import annotations

import pytest

from rekrutacja import (
    Kandydat,
    Oddzial,
    ParametrySymulacji,
    WynikiEgzaminu,
    generuj_miasto,
    przydziel,
    przydziel_naiwnie,
    punkty,
    punkty_egzamin,
    punkty_oceny,
    rozbicie_punktow,
    znajdz_pary_blokujace,
)


# ---------------------------------------------------------------------------
# Pomocnicze budowanie kandydatów
# ---------------------------------------------------------------------------


def _oceny(**kw: int) -> dict[str, int]:
    baza = {
        "polski": 4, "matematyka": 4, "jezyk_obcy": 4, "fizyka": 4,
        "chemia": 4, "biologia": 4, "geografia": 4, "historia": 4,
        "informatyka": 4, "wos": 4, "angielski": 4,
    }
    baza.update(kw)
    return baza


def _kandydat(k_id: int, oceny: dict[str, int], egz=(60, 60, 60), **kw) -> Kandydat:
    return Kandydat(
        id=k_id,
        imie=f"K{k_id}",
        egzamin=WynikiEgzaminu(*egz),
        oceny=oceny,
        preferencje=kw.pop("preferencje", []),
        **kw,
    )


# ---------------------------------------------------------------------------
# 1. Poprawność punktacji — ręcznie policzone przykłady
# ---------------------------------------------------------------------------


def test_punkty_egzamin_recznie():
    # polski 90, matma 80, obcy 70 -> 90*0.35 + 80*0.35 + 70*0.30
    # = 31.5 + 28.0 + 21.0 = 80.5
    k = _kandydat(1, _oceny(), egz=(90, 80, 70))
    assert punkty_egzamin(k) == pytest.approx(80.5)


def test_punkty_oceny_recznie():
    # oddział biol-chem: przedmioty polski, matma, biologia, chemia
    # oceny: polski 6(18), matma 5(17), biologia 4(14), chemia 3(8) = 57
    odd = Oddzial(0, 0, "biol-chem", ("biologia", "chemia"), 30)
    k = _kandydat(1, _oceny(polski=6, matematyka=5, biologia=4, chemia=3))
    assert punkty_oceny(k, odd) == 57.0


def test_punkty_zaleza_od_oddzialu():
    # Ten sam kandydat, dwa różne oddziały -> różne punkty za oceny.
    k = _kandydat(
        1,
        _oceny(polski=5, matematyka=5, biologia=6, chemia=6, historia=3, wos=2),
        egz=(60, 60, 60),
    )
    biol_chem = Oddzial(0, 0, "biol-chem", ("biologia", "chemia"), 30)
    human = Oddzial(1, 0, "human", ("historia", "wos"), 30)
    # biol-chem: 17+17+18+18 = 70 ; human: 17+17+8+2 = 44
    assert punkty_oceny(k, biol_chem) == 70.0
    assert punkty_oceny(k, human) == 44.0
    assert punkty(k, biol_chem) > punkty(k, human)


def test_pelna_punktacja_recznie():
    # Egzamin: 100/100/100 -> 100 pkt.
    # Oceny (biol-chem) same celujące: 4*18 = 72.
    # Wyróżnienie +7, wolontariat +3, konkursy 18 -> 28. Suma = 200 (maks).
    odd = Oddzial(0, 0, "biol-chem", ("biologia", "chemia"), 30)
    k = _kandydat(
        1,
        _oceny(polski=6, matematyka=6, biologia=6, chemia=6),
        egz=(100, 100, 100),
        swiadectwo_z_wyroznieniem=True,
        wolontariat=True,
        punkty_za_konkursy=18,
    )
    assert punkty(k, odd) == pytest.approx(200.0)


def test_konkursy_ograniczone_do_18():
    odd = Oddzial(0, 0, "biol-chem", ("biologia", "chemia"), 30)
    k = _kandydat(1, _oceny(), punkty_za_konkursy=99)
    r = rozbicie_punktow(k, odd)
    assert r.konkursy == 18.0


# ---------------------------------------------------------------------------
# 2. Deferred acceptance — własności
# ---------------------------------------------------------------------------


def _male_miasto():
    return generuj_miasto(
        ParametrySymulacji(
            seed=7,
            liczba_szkol=6,
            oddzialy_min=2,
            oddzialy_max=4,
            liczba_kandydatow=120,
            stosunek_miejsc=0.9,
            max_szkol_na_liscie=3,
        )
    )


def test_unikalnosc_przydzialu():
    m = _male_miasto()
    wynik = przydziel(m.kandydaci, m.oddzialy, seed=m.parametry.seed)
    # każdy kandydat pojawia się dokładnie raz
    ids = [w.kandydat_id for w in wynik.przydzial]
    assert sorted(ids) == sorted(k.id for k in m.kandydaci)
    # przydzielony oddział jest na liście preferencji kandydata
    kand = {k.id: k for k in m.kandydaci}
    for w in wynik.przydzial:
        if w.oddzial_id is not None:
            assert w.oddzial_id in kand[w.kandydat_id].preferencje
            assert kand[w.kandydat_id].preferencje[w.numer_preferencji] == w.oddzial_id


def test_determinizm_przy_seedzie():
    m = _male_miasto()
    w1 = przydziel(m.kandydaci, m.oddzialy, seed=1)
    w2 = przydziel(m.kandydaci, m.oddzialy, seed=1)
    a = {w.kandydat_id: w.oddzial_id for w in w1.przydzial}
    b = {w.kandydat_id: w.oddzial_id for w in w2.przydzial}
    assert a == b
    assert w1.liczba_rund == w2.liczba_rund


def test_generator_determinizm():
    m1 = generuj_miasto(ParametrySymulacji(seed=123, liczba_kandydatow=80))
    m2 = generuj_miasto(ParametrySymulacji(seed=123, liczba_kandydatow=80))
    assert [k.preferencje for k in m1.kandydaci] == [k.preferencje for k in m2.kandydaci]
    assert [o.limit_miejsc for o in m1.oddzialy] == [o.limit_miejsc for o in m2.oddzialy]


def test_stabilnosc_matchingu():
    """Nie istnieje para blokująca: kandydat woli oddział od swojego przydziału
    i miałby w nim więcej punktów niż ostatni zakwalifikowany."""
    m = _male_miasto()
    wynik = przydziel(m.kandydaci, m.oddzialy, seed=m.parametry.seed)
    pary = znajdz_pary_blokujace(wynik.przydzial, m.kandydaci, m.oddzialy)
    assert pary == [], f"Znaleziono {len(pary)} par blokujących: {pary[:3]}"


def test_stabilnosc_recznie_maly_przypadek():
    """Ręcznie zbudowany, przekrojowy przypadek z wypychaniem."""
    odd_a = Oddzial(0, 0, "A", ("biologia", "chemia"), 1)  # 1 miejsce
    odd_b = Oddzial(1, 1, "B", ("fizyka", "informatyka"), 1)  # 1 miejsce
    # Trzej kandydaci; wszyscy najpierw chcą do A.
    # Punkty w A rosną z ocenami biol/chem; różnicujemy egzaminem.
    k1 = _kandydat(1, _oceny(), egz=(90, 90, 90), preferencje=[0, 1])
    k2 = _kandydat(2, _oceny(), egz=(70, 70, 70), preferencje=[0, 1])
    k3 = _kandydat(3, _oceny(), egz=(50, 50, 50), preferencje=[0, 1])
    wynik = przydziel([k1, k2, k3], [odd_a, odd_b], seed=1)
    przyd = {w.kandydat_id: w.oddzial_id for w in wynik.przydzial}
    # Najlepszy do A, drugi wypchnięty do B, trzeci nigdzie.
    assert przyd[1] == 0
    assert przyd[2] == 1
    assert przyd[3] is None
    pary = znajdz_pary_blokujace(wynik.przydzial, [k1, k2, k3], [odd_a, odd_b])
    assert pary == []


def test_niedobor_chetnych_wszyscy_wchodza():
    odd = Oddzial(0, 0, "A", ("biologia", "chemia"), 10)
    kand = [_kandydat(i, _oceny(), preferencje=[0]) for i in range(3)]
    wynik = przydziel(kand, [odd], seed=1)
    assert all(w.oddzial_id == 0 for w in wynik.przydzial)
    # brak progu przy niedoborze chętnych
    assert wynik.progi_koncowe[0] is None


def test_olimpijczyk_poza_limitem():
    """Laureat wchodzi do 1. preferencji nawet gdy limit wyczerpany punktowo."""
    odd = Oddzial(0, 0, "A", ("biologia", "chemia"), 1)
    # mocny "zwykły" kandydat
    mocny = _kandydat(1, _oceny(polski=6, matematyka=6, biologia=6, chemia=6),
                      egz=(100, 100, 100), preferencje=[0])
    # słaby laureat
    laureat = _kandydat(2, _oceny(polski=2, matematyka=2, biologia=2, chemia=2),
                        egz=(10, 10, 10), preferencje=[0], laureat_olimpiady=True)
    wynik = przydziel([mocny, laureat], [odd], seed=1)
    przyd = {w.kandydat_id: w.oddzial_id for w in wynik.przydzial}
    # obaj przyjęci — laureat poza limitem
    assert przyd[1] == 0
    assert przyd[2] == 0


def test_tryb_naiwny_gorszy_i_niestabilny():
    """Tryb naiwny produkuje pary blokujące (niestabilność); DA nie."""
    m = _male_miasto()
    naiwny = przydziel_naiwnie(m.kandydaci, m.oddzialy, seed=m.parametry.seed)
    da = przydziel(m.kandydaci, m.oddzialy, seed=m.parametry.seed)

    pary_naiwny = znajdz_pary_blokujace(naiwny, m.kandydaci, m.oddzialy)
    pary_da = znajdz_pary_blokujace(da.przydzial, m.kandydaci, m.oddzialy)

    assert pary_da == []
    assert len(pary_naiwny) > 0  # naiwny jest niestabilny

    # liczba zakwalifikowanych w DA nie mniejsza niż w naiwnym
    zakw_da = sum(1 for w in da.przydzial if w.oddzial_id is not None)
    zakw_naiwny = sum(1 for w in naiwny if w.oddzial_id is not None)
    assert zakw_da >= zakw_naiwny


def test_log_rund_spojny():
    m = _male_miasto()
    wynik = przydziel(m.kandydaci, m.oddzialy, seed=m.parametry.seed)
    assert wynik.liczba_rund >= 1
    # migawka ostatniej rundy zgadza się z ostatecznym przydziałem
    ostatnia = wynik.rundy[-1]
    for w in wynik.przydzial:
        assert ostatnia.przydzial[w.kandydat_id] == w.oddzial_id


def test_pusta_lista_preferencji_niezakwalifikowany():
    odd = Oddzial(0, 0, "A", ("biologia", "chemia"), 5)
    k = _kandydat(1, _oceny(), preferencje=[])
    wynik = przydziel([k], [odd], seed=1)
    assert wynik.przydzial[0].oddzial_id is None
