"""Generator danych syntetycznych ze seedem.

Tworzy spójne miasto: szkoły o różnym prestiżu, oddziały o różnych profilach
(parach przedmiotów punktowanych) i limitach, oraz kandydatów, których wyniki
egzaminu i oceny są skorelowane (jeden czynnik zdolności + szum). Model
preferencji sprawia, że powstają realistyczne oblegane i niedobrane oddziały.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .modele import (
    UNIWERSUM_PRZEDMIOTOW,
    Kandydat,
    Oddzial,
    Szkola,
    WynikiEgzaminu,
)

# Katalog profili: nazwa -> dwa dodatkowe przedmioty punktowane
# (poza polskim i matematyką, które liczą się zawsze).
PROFILE: dict[str, tuple[str, str]] = {
    "biologiczno-chemiczny": ("biologia", "chemia"),
    "matematyczno-fizyczny": ("fizyka", "informatyka"),
    "humanistyczny": ("historia", "wos"),
    "geograficzno-językowy": ("geografia", "angielski"),
    "matematyczno-geograficzny": ("geografia", "jezyk_obcy"),
    "biologiczno-geograficzny": ("biologia", "geografia"),
    "lingwistyczny": ("jezyk_obcy", "angielski"),
    "politechniczny": ("fizyka", "chemia"),
}

# Który profil odpowiada jakiej "osi zdolności" (do modelu dopasowania).
# 0 = ścisła, 1 = humanistyczna. Kandydat ma swoją oś preferencji.
PROFIL_OS: dict[str, float] = {
    "biologiczno-chemiczny": 0.25,
    "matematyczno-fizyczny": 0.0,
    "humanistyczny": 1.0,
    "geograficzno-językowy": 0.7,
    "matematyczno-geograficzny": 0.35,
    "biologiczno-geograficzny": 0.55,
    "lingwistyczny": 0.85,
    "politechniczny": 0.1,
}

IMIONA = [
    "Ala", "Bartek", "Cela", "Darek", "Ela", "Filip", "Gosia", "Hubert",
    "Iga", "Janek", "Kasia", "Leon", "Marta", "Norbert", "Ola", "Piotr",
    "Renata", "Szymon", "Tola", "Ula", "Wojtek", "Zosia", "Adam", "Basia",
]


@dataclass
class ParametrySymulacji:
    """Parametry sterujące generatorem (mapują się na sidebar Streamlit)."""

    seed: int = 42
    liczba_szkol: int = 10
    oddzialy_min: int = 2
    oddzialy_max: int = 5
    liczba_kandydatow: int = 300
    stosunek_miejsc: float = 1.0  # miejsca / kandydaci
    max_szkol_na_liscie: int = 3
    srednia_dlugosc_listy: float = 5.0  # średnia liczba oddziałów na liście


@dataclass
class Miasto:
    """Wygenerowany zestaw danych."""

    szkoly: list[Szkola]
    oddzialy: list[Oddzial]
    kandydaci: list[Kandydat]
    parametry: ParametrySymulacji

    @property
    def oddzialy_wg_id(self) -> dict[int, Oddzial]:
        return {o.id: o for o in self.oddzialy}

    @property
    def szkoly_wg_id(self) -> dict[int, Szkola]:
        return {s.id: s for s in self.szkoly}


def _ocena_z_umiejetnosci(u: float, rng: np.random.Generator) -> int:
    """Mapuje ukrytą umiejętność w przedmiocie (z-score) na ocenę 2–6."""
    # progi tak dobrane, by rozkład ocen był realistyczny (dużo 4–5).
    szum = rng.normal(0, 0.5)
    v = u + szum
    if v > 1.3:
        return 6
    if v > 0.4:
        return 5
    if v > -0.5:
        return 4
    if v > -1.4:
        return 3
    return 2


def _procent_z_umiejetnosci(u: float, rng: np.random.Generator) -> float:
    """Mapuje ukrytą umiejętność (z-score) na wynik egzaminu w procentach."""
    # średnia ~62%, odchylenie ~18 pkt proc.; obcinamy do [0, 100].
    v = 62 + 18 * u + rng.normal(0, 6)
    return float(np.clip(round(v), 0, 100))


def generuj_miasto(p: ParametrySymulacji) -> Miasto:
    """Buduje spójne miasto: szkoły, oddziały, kandydatów."""
    rng = np.random.default_rng(p.seed)

    # --- Szkoły i oddziały ---
    szkoly: list[Szkola] = []
    oddzialy: list[Oddzial] = []
    oddzial_id = 0
    nazwy_profili = list(PROFILE.keys())

    for s_id in range(p.liczba_szkol):
        # Prestiż: liceum ogólne od najbardziej do mniej renomowanego.
        prestiz = float(rng.normal(0, 1))
        szkola = Szkola(
            id=s_id,
            nazwa=f"LO {s_id + 1}",
            prestiz=prestiz,
        )
        n_odd = int(rng.integers(p.oddzialy_min, p.oddzialy_max + 1))
        wybrane_profile = rng.choice(
            nazwy_profili, size=min(n_odd, len(nazwy_profili)), replace=False
        )
        for profil in wybrane_profile:
            limit = int(rng.integers(20, 33))  # 20–32 miejsc w oddziale
            oddzialy.append(
                Oddzial(
                    id=oddzial_id,
                    szkola_id=s_id,
                    nazwa_profilu=str(profil),
                    przedmioty_punktowane=PROFILE[str(profil)],
                    limit_miejsc=limit,
                )
            )
            szkola.oddzialy.append(oddzial_id)
            oddzial_id += 1
        szkoly.append(szkola)

    # --- Skalowanie limitów do zadanego stosunku miejsc/kandydatów ---
    laczne_miejsca = sum(o.limit_miejsc for o in oddzialy)
    cel_miejsc = p.stosunek_miejsc * p.liczba_kandydatow
    if laczne_miejsca > 0:
        skala = cel_miejsc / laczne_miejsca
        for o in oddzialy:
            o.limit_miejsc = max(5, int(round(o.limit_miejsc * skala)))

    # --- Kandydaci ---
    kandydaci: list[Kandydat] = []
    for k_id in range(p.liczba_kandydatow):
        sila = float(rng.normal(0, 1))  # ogólny czynnik zdolności
        # Oś zainteresowań kandydata (0 ścisła … 1 humanistyczna).
        os_zainteresowan = float(rng.uniform(0, 1))

        # Umiejętność w przedmiocie = ogólna siła + składnik profilowy.
        oceny: dict[str, int] = {}
        for przedmiot in UNIWERSUM_PRZEDMIOTOW:
            # przedmioty "ścisłe" korzystają, gdy oś bliska 0; "humanist." gdy bliska 1.
            os_przedmiotu = {
                "matematyka": 0.0, "fizyka": 0.0, "informatyka": 0.1,
                "chemia": 0.2, "biologia": 0.4, "geografia": 0.5,
                "jezyk_obcy": 0.8, "angielski": 0.8, "polski": 0.9,
                "historia": 1.0, "wos": 1.0,
            }.get(przedmiot, 0.5)
            dopasowanie = 1.0 - abs(os_zainteresowan - os_przedmiotu)
            u = sila + 0.6 * (dopasowanie - 0.5)
            oceny[przedmiot] = _ocena_z_umiejetnosci(u, rng)

        egzamin = WynikiEgzaminu(
            polski=_procent_z_umiejetnosci(sila + 0.3 * (os_zainteresowan - 0.5), rng),
            matematyka=_procent_z_umiejetnosci(sila - 0.3 * (os_zainteresowan - 0.5), rng),
            jezyk_obcy=_procent_z_umiejetnosci(sila + 0.15 * (os_zainteresowan - 0.5), rng),
        )

        kandydat = Kandydat(
            id=k_id,
            imie=f"{IMIONA[k_id % len(IMIONA)]} {k_id + 1:03d}",
            egzamin=egzamin,
            oceny=oceny,
            swiadectwo_z_wyroznieniem=bool(rng.random() < _p_wyroznienie(sila)),
            wolontariat=bool(rng.random() < 0.45),
            punkty_za_konkursy=_konkursy(sila, rng),
            laureat_olimpiady=bool(rng.random() < _p_laureat(sila)),
            finalista_olimpiady=bool(rng.random() < _p_finalista(sila)),
            problemy_zdrowotne=bool(rng.random() < 0.05),
            kryteria_ex_aequo=int(rng.binomial(4, 0.12)),
            sila=sila,
            preferencje=[],  # uzupełnimy niżej
        )
        kandydaci.append(kandydat)

    # --- Preferencje ---
    _wygeneruj_preferencje(kandydaci, szkoly, oddzialy, rng, p)

    return Miasto(szkoly=szkoly, oddzialy=oddzialy, kandydaci=kandydaci, parametry=p)


def _p_wyroznienie(sila: float) -> float:
    # świadectwo z wyróżnieniem: średnia ≥4,75 — rośnie z siłą.
    return float(np.clip(0.2 + 0.25 * sila, 0.01, 0.85))


def _p_laureat(sila: float) -> float:
    return float(np.clip(0.015 + 0.02 * (sila - 1.0), 0.0, 0.06))


def _p_finalista(sila: float) -> float:
    return float(np.clip(0.03 + 0.03 * (sila - 0.5), 0.0, 0.1))


def _konkursy(sila: float, rng: np.random.Generator) -> int:
    if rng.random() < np.clip(0.15 + 0.15 * sila, 0.02, 0.6):
        return int(rng.integers(1, 19))
    return 0


def _wygeneruj_preferencje(
    kandydaci: list[Kandydat],
    szkoly: list[Szkola],
    oddzialy: list[Oddzial],
    rng: np.random.Generator,
    p: ParametrySymulacji,
) -> None:
    """Buduje uporządkowane listy preferencji.

    Atrakcyjność oddziału dla kandydata rośnie z prestiżem szkoły i z
    dopasowaniem profilu do siły/zainteresowań kandydata; dochodzi szum.
    Ograniczenie: co najwyżej ``max_szkol_na_liscie`` różnych szkół.
    """
    szkoly_wg_id = {s.id: s for s in szkoly}

    for k in kandydaci:
        atrakcyjnosc: list[tuple[float, int]] = []
        for o in oddzialy:
            szkola = szkoly_wg_id[o.szkola_id]
            # dopasowanie profilu: im lepsze oceny w przedmiotach profilu, tym lepiej
            oceny_profilu = np.mean(
                [k.oceny[pp] for pp in o.przedmioty_punktowane]
            )
            dopasowanie = (oceny_profilu - 4.0)  # ~[-2, 2]
            # silni kandydaci mocniej ciągną do prestiżowych szkół, ale
            # gust jest w dużej mierze idiosynkratyczny (duży szum), dzięki
            # czemu preferencje się różnicują i nie wszyscy tłoczą się w tych
            # samych 2-3 szkołach.
            waga_prestizu = 0.7 + 0.4 * max(0.0, k.sila)
            wartosc = (
                waga_prestizu * szkola.prestiz
                + 1.0 * dopasowanie
                + rng.normal(0, 1.6)  # szum (indywidualny gust)
            )
            atrakcyjnosc.append((float(wartosc), o.id))

        atrakcyjnosc.sort(reverse=True)

        # Losowa docelowa długość listy (min 1).
        dlugosc = int(np.clip(rng.poisson(p.srednia_dlugosc_listy), 1, len(oddzialy)))

        lista: list[int] = []
        szkoly_na_liscie: set[int] = set()
        oddzialy_wg_id = {o.id: o for o in oddzialy}
        for _, oid in atrakcyjnosc:
            if len(lista) >= dlugosc:
                break
            szk = oddzialy_wg_id[oid].szkola_id
            if szk not in szkoly_na_liscie and len(szkoly_na_liscie) >= p.max_szkol_na_liscie:
                continue  # limit różnych szkół wyczerpany
            lista.append(oid)
            szkoly_na_liscie.add(szk)

        k.preferencje = lista
