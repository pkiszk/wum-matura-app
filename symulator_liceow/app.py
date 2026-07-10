"""Symulator rekrutacji do liceów — aplikacja wykładowa (Streamlit).

Uruchomienie:
    cd symulator_liceow
    streamlit run app.py

Aplikacja pokazuje krok po kroku, jak z punktów kandydatów, list preferencji i
limitów miejsc powstaje ostateczny przydział do oddziałów (klas) w liceach —
z iteracyjnym przesuwaniem kandydatów między oddziałami (algorytm Gale-Shapley,
student-proposing deferred acceptance).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from rekrutacja import (
    NAZWY_PRZEDMIOTOW,
    ParametrySymulacji,
    generuj_miasto,
    kandydaci_na_miejsce,
    podsumowanie_przydzialu,
    przydziel,
    przydziel_naiwnie,
    punkty,
    rozbicie_punktow,
    znajdz_pary_blokujace,
)
from rekrutacja.matching import ranking_oddzialu, _losy_kandydatow
import wykresy

st.set_page_config(
    page_title="Symulator rekrutacji do liceów",
    page_icon="🎓",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Obliczenia (przeliczane tylko po zmianie parametrów lub seeda)
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner="Generuję miasto i liczę przydział…")
def policz(params_tuple: tuple):
    (seed, liczba_szkol, oddz_min, oddz_max, liczba_kand,
     stosunek, max_szkol, srednia_listy) = params_tuple
    p = ParametrySymulacji(
        seed=seed,
        liczba_szkol=liczba_szkol,
        oddzialy_min=oddz_min,
        oddzialy_max=oddz_max,
        liczba_kandydatow=liczba_kand,
        stosunek_miejsc=stosunek,
        max_szkol_na_liscie=max_szkol,
        srednia_dlugosc_listy=srednia_listy,
    )
    miasto = generuj_miasto(p)
    wynik = przydziel(miasto.kandydaci, miasto.oddzialy, seed=seed)
    naiwny = przydziel_naiwnie(miasto.kandydaci, miasto.oddzialy, seed=seed)
    return miasto, wynik, naiwny


def etykieta_oddzialu(miasto, oid: int) -> str:
    o = miasto.oddzialy_wg_id[oid]
    s = miasto.szkoly_wg_id[o.szkola_id]
    return f"{s.nazwa} · {o.nazwa_profilu}"


def przedmioty_str(o) -> str:
    return " + ".join(NAZWY_PRZEDMIOTOW[p] for p in o.wszystkie_przedmioty_punktowane)


# ---------------------------------------------------------------------------
# Sidebar — parametry symulacji
# ---------------------------------------------------------------------------

st.sidebar.title("⚙️ Parametry symulacji")
st.sidebar.caption("Zmiana dowolnego parametru przelicza cały przydział.")

seed = st.sidebar.number_input("Ziarno losowe (seed)", 0, 10_000, 42, step=1)
liczba_szkol = st.sidebar.slider("Liczba szkół", 5, 30, 10)
oddz_zakres = st.sidebar.slider("Oddziały na szkołę (zakres)", 2, 6, (2, 5))
liczba_kand = st.sidebar.slider("Liczba kandydatów", 50, 2000, 400, step=50)
stosunek = st.sidebar.slider(
    "Stosunek miejsc do kandydatów", 0.5, 1.5, 1.0, step=0.05,
    help="1.0 = tyle samo miejsc co kandydatów. Poniżej 1.0 — więcej chętnych niż miejsc.",
)
max_szkol = st.sidebar.slider("Maks. liczba szkół na liście preferencji", 1, 10, 3)
srednia_listy = st.sidebar.slider("Średnia długość listy (oddziały)", 1.0, 12.0, 5.0, step=0.5)

params = (
    int(seed), int(liczba_szkol), int(oddz_zakres[0]), int(oddz_zakres[1]),
    int(liczba_kand), float(stosunek), int(max_szkol), float(srednia_listy),
)

miasto, wynik, naiwny = policz(params)
losy = _losy_kandydatow(miasto.kandydaci, int(seed))
pod_da = podsumowanie_przydzialu(wynik.przydzial)
pod_naiwny = podsumowanie_przydzialu(naiwny)

st.sidebar.divider()
st.sidebar.metric("Oddziałów (klas)", len(miasto.oddzialy))
st.sidebar.metric("Łączna liczba miejsc", sum(o.limit_miejsc for o in miasto.oddzialy))
st.sidebar.metric("Liczba rund algorytmu", wynik.liczba_rund)


# ---------------------------------------------------------------------------
# Nagłówek
# ---------------------------------------------------------------------------

st.title("🎓 Symulator rekrutacji do liceów")
st.markdown(
    "Materiał wykładowy pokazujący **krok po kroku**, jak z punktów kandydatów, "
    "list preferencji i limitów miejsc powstaje ostateczny przydział do oddziałów "
    "(klas) w liceach. Model odwzorowuje polskie zasady rekrutacji (rozporządzenie "
    "MEN 2025, ustawa *Prawo oświatowe*)."
)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "1 · Miasto i kandydaci",
        "2 · Listy preferencji",
        "3 · Listy rankingowe",
        "4 · Symulacja krok po kroku",
        "5 · Wynik końcowy",
        "6 · Runda uzupełniająca",
    ]
)


# ===========================================================================
# TAB 1 — Miasto i kandydaci
# ===========================================================================

with tab1:
    st.header("Miasto: szkoły i oddziały")
    st.markdown(
        "**Jednostką rekrutacji jest oddział** — profil klasy w konkretnej szkole. "
        "Każdy oddział ma własny **limit miejsc** i własną **parę przedmiotów "
        "punktowanych** (poza językiem polskim i matematyką, które liczą się zawsze)."
    )

    wiersze = []
    for o in miasto.oddzialy:
        s = miasto.szkoly_wg_id[o.szkola_id]
        wiersze.append(
            {
                "Szkoła": s.nazwa,
                "Profil": o.nazwa_profilu,
                "Przedmioty punktowane (4)": przedmioty_str(o),
                "Limit miejsc": o.limit_miejsc,
                "Prestiż szkoły": round(s.prestiz, 2),
            }
        )
    st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)

    st.header("Rozkład punktów kandydatów")
    st.markdown(
        "Maksymalnie **200 punktów**: egzamin ósmoklasisty (max 100) + oceny z 4 "
        "przedmiotów (max 72) + osiągnięcia (max 28). **Uwaga:** punkty zależą od "
        "oddziału, bo różni się para przedmiotów punktowanych — histogram poniżej "
        "liczy punkty dla oddziału **1. wyboru** każdego kandydata."
    )
    st.plotly_chart(wykresy.histogram_punktow(miasto), width="stretch")

    st.header("Karta kandydata — te same oceny, różne punkty w różnych oddziałach")
    st.markdown(
        "To **fundament modelu**: ten sam kandydat ma **inną liczbę punktów** w "
        "dwóch oddziałach, bo liczą się inne przedmioty ze świadectwa."
    )

    kand_opcje = {f"{k.imie}": k.id for k in miasto.kandydaci}
    wyb_kand = st.selectbox("Wybierz kandydata", list(kand_opcje.keys()), key="karta_kand")
    k = next(k for k in miasto.kandydaci if k.id == kand_opcje[wyb_kand])

    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Egzamin: polski", f"{k.egzamin.polski:.0f}%")
    c1.metric("Egzamin: matematyka", f"{k.egzamin.matematyka:.0f}%")
    c2.metric("Egzamin: język obcy", f"{k.egzamin.jezyk_obcy:.0f}%")
    dod = []
    if k.swiadectwo_z_wyroznieniem:
        dod.append("wyróżnienie +7")
    if k.wolontariat:
        dod.append("wolontariat +3")
    if k.punkty_za_konkursy:
        dod.append(f"konkursy +{min(k.punkty_za_konkursy, 18)}")
    if k.olimpijczyk:
        dod.append("🏅 olimpijczyk")
    c3.metric("Osiągnięcia", ", ".join(dod) if dod else "brak")

    # dwa oddziały do porównania — najlepiej o różnych profilach
    profile_ids = {}
    for o in miasto.oddzialy:
        profile_ids.setdefault(o.nazwa_profilu, o.id)
    opcje_odd = {etykieta_oddzialu(miasto, o.id): o.id for o in miasto.oddzialy}
    lista_opcji = list(opcje_odd.keys())
    colA, colB = st.columns(2)
    with colA:
        oA = st.selectbox("Oddział A", lista_opcji, index=0, key="oddA")
    with colB:
        idxB = 1 if len(lista_opcji) > 1 else 0
        oB = st.selectbox("Oddział B", lista_opcji, index=idxB, key="oddB")

    def karta_punktow(col, oid):
        o = miasto.oddzialy_wg_id[oid]
        r = rozbicie_punktow(k, o)
        with col:
            st.markdown(f"**{etykieta_oddzialu(miasto, oid)}**")
            st.caption("Przedmioty punktowane: " + przedmioty_str(o))
            szczegoly = pd.DataFrame(
                [
                    {"Przedmiot": NAZWY_PRZEDMIOTOW[p], "Ocena": oc, "Punkty": pk}
                    for p, (oc, pk) in r.oceny_szczegoly.items()
                ]
            )
            st.dataframe(szczegoly, width="stretch", hide_index=True)
            st.write(
                f"Egzamin: **{r.egzamin:.1f}** · Oceny: **{r.oceny:.0f}** · "
                f"Dodatkowe: **{r.dodatkowe:.0f}**"
            )
            st.metric("Razem punktów", f"{r.suma:.1f} / 200")

    karta_punktow(colA, opcje_odd[oA])
    karta_punktow(colB, opcje_odd[oB])

    roznica = abs(
        punkty(k, miasto.oddzialy_wg_id[opcje_odd[oA]])
        - punkty(k, miasto.oddzialy_wg_id[opcje_odd[oB]])
    )
    st.info(
        f"Różnica punktów tego samego kandydata między oddziałami: **{roznica:.1f} pkt** "
        "— wynika wyłącznie z różnych przedmiotów punktowanych."
    )


# ===========================================================================
# TAB 2 — Listy preferencji
# ===========================================================================

with tab2:
    st.header("Listy preferencji kandydatów")
    st.markdown(
        "Każdy kandydat składa **jedną uporządkowaną listę** oddziałów. Oddziały "
        "różnych szkół mogą się przeplatać. Liczba różnych szkół na liście jest "
        f"ograniczona (tu: maks. **{max_szkol}**)."
    )
    st.plotly_chart(wykresy.histogram_dlugosci_list(miasto), width="stretch")

    st.header("Popularność oddziałów")
    st.markdown(
        "Miara oblegania: ilu kandydatów wskazało dany oddział **gdziekolwiek** na "
        "liście, podzielone przez limit miejsc. Wartości **powyżej 1** (czerwone) to "
        "oddziały oblegane; **poniżej 1** (zielone) — z ryzykiem niedoboru chętnych."
    )
    cnm = kandydaci_na_miejsce(miasto.kandydaci, miasto.oddzialy)
    st.plotly_chart(wykresy.wykres_popularnosci(miasto, cnm), width="stretch")

    with st.expander("Zobacz przykładowe listy preferencji"):
        prob = miasto.kandydaci[: min(15, len(miasto.kandydaci))]
        wiersze = []
        for k in prob:
            wiersze.append(
                {
                    "Kandydat": k.imie,
                    "Lista preferencji": " → ".join(
                        etykieta_oddzialu(miasto, oid) for oid in k.preferencje
                    ) or "(pusta)",
                }
            )
        st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)


# ===========================================================================
# TAB 3 — Listy rankingowe
# ===========================================================================

with tab3:
    st.header("Listy rankingowe oddziałów")
    st.markdown(
        "W każdym oddziale kandydaci są **sortowani malejąco po punktach** (liczonych "
        "dla tego oddziału). Przy remisie decyduje tie-break: problemy zdrowotne → "
        "kryteria ex aequo → losowanie. **Linia odcięcia** to limit miejsc — próg "
        "punktowy nie jest zadany z góry, wyłania się z rankingu."
    )

    opcje_odd = {etykieta_oddzialu(miasto, o.id): o.id for o in miasto.oddzialy}
    wyb = st.selectbox("Wybierz oddział", list(opcje_odd.keys()), key="rank_odd")
    oid = opcje_odd[wyb]
    o = miasto.oddzialy_wg_id[oid]

    st.caption(
        f"Przedmioty punktowane: {przedmioty_str(o)} · Limit miejsc: {o.limit_miejsc}"
    )

    # wszyscy kandydaci, którzy mają ten oddział na liście
    chetni = [k for k in miasto.kandydaci if oid in k.preferencje]
    ranking = ranking_oddzialu(chetni, o, losy)

    wiersze = []
    for poz, kk in enumerate(ranking, start=1):
        wiersze.append(
            {
                "Pozycja": poz,
                "Kandydat": kk.imie,
                "Punkty": round(punkty(kk, o), 1),
                "Olimpijczyk": "🏅" if kk.olimpijczyk else "",
                "Problemy zdrow.": "✓" if kk.problemy_zdrowotne else "",
                "Kryteria ex aequo": kk.kryteria_ex_aequo,
                "W limicie?": "✅ tak" if poz <= o.limit_miejsc else "❌ nie",
            }
        )
    df = pd.DataFrame(wiersze)
    st.dataframe(df, width="stretch", hide_index=True, height=440)

    if len(ranking) > o.limit_miejsc:
        prog = round(punkty(ranking[o.limit_miejsc - 1], o), 1)
        st.success(
            f"Chętnych: **{len(ranking)}** na **{o.limit_miejsc}** miejsc. "
            f"Gdyby wszyscy chcieli tu jako 1. wybór, próg wyniósłby **{prog} pkt** "
            "(punkty ostatniego w limicie)."
        )
    else:
        st.info(
            f"Chętnych: **{len(ranking)}** ≤ **{o.limit_miejsc}** miejsc — "
            "wchodzą wszyscy, brak progu."
        )


# ===========================================================================
# TAB 4 — Symulacja krok po kroku
# ===========================================================================

with tab4:
    st.header("Symulacja przydziału krok po kroku")
    st.markdown(
        "Algorytm **deferred acceptance** (Gale-Shapley, student-proposing): kandydat "
        "jest tymczasowo kwalifikowany do najwyższej preferencji, w której mieści się "
        "w limicie. Kandydat **wypchnięty** przez kogoś z wyższą pozycją spada do "
        "kolejnej preferencji i sam może wypychać innych. Iterujemy do punktu stałego."
    )

    maks_runda = wynik.liczba_rund

    # Jedno źródło prawdy = klucz slidera. Inicjalizacja i przycięcie do
    # aktualnego zakresu MUSZĄ nastąpić przed utworzeniem widgetów (zmiana
    # parametrów może zmniejszyć liczbę rund).
    if "runda_slider" not in st.session_state:
        st.session_state.runda_slider = 1
    st.session_state.runda_slider = min(
        max(1, int(st.session_state.runda_slider)), maks_runda
    )

    def _poprzednia_runda():
        st.session_state.runda_slider = max(1, st.session_state.runda_slider - 1)

    def _nastepna_runda():
        st.session_state.runda_slider = min(
            maks_runda, st.session_state.runda_slider + 1
        )

    cprev, cslider, cnext = st.columns([1, 6, 1])
    with cprev:
        st.write("")
        st.button(
            "◀ Poprzednia", width="stretch", on_click=_poprzednia_runda,
            disabled=st.session_state.runda_slider <= 1,
        )
    with cnext:
        st.write("")
        st.button(
            "Następna ▶", width="stretch", on_click=_nastepna_runda,
            disabled=st.session_state.runda_slider >= maks_runda,
        )
    with cslider:
        if maks_runda > 1:
            # value nie jest podawane — widget czyta stan z klucza runda_slider,
            # dzięki czemu callbacki przycisków nie są nadpisywane.
            st.slider("Runda", 1, maks_runda, key="runda_slider")
        else:
            st.caption("Algorytm zbiegł w jednej rundzie — brak kolejnych kroków.")

    numer_rundy = st.session_state.runda_slider
    r_idx = numer_rundy - 1
    runda = wynik.rundy[r_idx]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Runda", f"{numer_rundy} / {maks_runda}")
    m2.metric("Zgłoszeń w tej rundzie", len(runda.zgloszenia))
    m3.metric("Zakwalifikowani tymczasowo", runda.liczba_zakwalifikowanych)
    m4.metric("Wypchnięci w tej rundzie", runda.liczba_wypchnietych)

    if runda.wypchniecia:
        with st.expander(f"Kto został wypchnięty w rundzie {numer_rundy}?", expanded=False):
            kand = {k.id: k for k in miasto.kandydaci}
            wiersze = []
            for w in runda.wypchniecia:
                dokad = (
                    "niezakwalifikowany"
                    if w.niezakwalifikowany
                    else (etykieta_oddzialu(miasto, w.spadl_do_oddzialu) if w.spadl_do_oddzialu is not None else "szuka dalej")
                )
                wiersze.append(
                    {
                        "Kandydat": kand[w.kandydat_id].imie,
                        "Wypchnięty z": etykieta_oddzialu(miasto, w.z_oddzialu),
                        "Przez": kand[w.przez_kogo].imie if w.przez_kogo is not None else "—",
                        "Trafił": dokad,
                    }
                )
            st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)

    st.subheader("Przepływ kandydatów między numerami preferencji")
    st.plotly_chart(wykresy.sankey_przeplyw(miasto, wynik, r_idx), width="stretch")

    st.subheader("Ewolucja progów punktowych")
    st.caption("Wybierz oddziały, których progi chcesz śledzić w czasie działania algorytmu.")
    opcje_odd = {etykieta_oddzialu(miasto, o.id): o.id for o in miasto.oddzialy}
    # domyślnie 3 najbardziej oblegane oddziały
    cnm = kandydaci_na_miejsce(miasto.kandydaci, miasto.oddzialy)
    domyslne_ids = [oid for oid, _ in sorted(cnm.items(), key=lambda x: x[1], reverse=True)[:3]]
    domyslne_etyk = [etykieta_oddzialu(miasto, oid) for oid in domyslne_ids]
    wybrane = st.multiselect(
        "Oddziały", list(opcje_odd.keys()), default=domyslne_etyk, key="progi_multi"
    )
    if wybrane:
        ids = [opcje_odd[e] for e in wybrane]
        st.plotly_chart(wykresy.wykres_progow(miasto, wynik, ids), width="stretch")
    else:
        st.info("Wybierz co najmniej jeden oddział, aby zobaczyć ewolucję progów.")

    st.subheader("🔍 Śledzenie jednego kandydata")
    kand_opcje = {k.imie: k.id for k in miasto.kandydaci}
    wyb_kand = st.selectbox("Kandydat do prześledzenia", list(kand_opcje.keys()), key="sledz_kand")
    kid = kand_opcje[wyb_kand]
    kk = next(k for k in miasto.kandydaci if k.id == kid)

    sciezka = []
    for i, rnd in enumerate(wynik.rundy, start=1):
        zgl = next((z for z in rnd.zgloszenia if z.kandydat_id == kid), None)
        wyp = next((w for w in rnd.wypchniecia if w.kandydat_id == kid), None)
        stan = rnd.przydzial.get(kid)
        sciezka.append(
            {
                "Runda": i,
                "Zgłosił się do": etykieta_oddzialu(miasto, zgl.do_oddzialu) + f" ({zgl.numer_preferencji + 1}. wybór)" if zgl else "—",
                "Wypchnięty?": ("tak, z " + etykieta_oddzialu(miasto, wyp.z_oddzialu)) if wyp else "",
                "Stan po rundzie": etykieta_oddzialu(miasto, stan) if stan is not None else "wolny / szuka",
            }
        )
    st.dataframe(pd.DataFrame(sciezka), width="stretch", hide_index=True)
    fin = wynik.przydzial_kandydata(kid)
    if fin.oddzial_id is not None:
        st.success(
            f"Ostatecznie: **{etykieta_oddzialu(miasto, fin.oddzial_id)}** "
            f"({(fin.numer_preferencji or 0) + 1}. wybór, {fin.punkty:.1f} pkt)."
        )
    else:
        st.error("Ostatecznie: **niezakwalifikowany** (wyczerpał listę preferencji).")


# ===========================================================================
# TAB 5 — Wynik końcowy
# ===========================================================================

with tab5:
    st.header("Wynik końcowy przydziału")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("W 1. preferencji", f"{pod_da.odsetek_preferencji(0):.0f}%")
    c2.metric("W 2. preferencji", f"{pod_da.odsetek_preferencji(1):.0f}%")
    c3.metric("W 3. preferencji", f"{pod_da.odsetek_preferencji(2):.0f}%")
    c4.metric("Niezakwalifikowani", f"{pod_da.odsetek_niezakwalifikowani:.0f}%")
    c5.metric("Liczba rund", wynik.liczba_rund)

    st.subheader("Porównanie z trybem naiwnym")
    st.markdown(
        "**Tryb naiwny** to pojedynczy przebieg **bez wypychania** (kandydat "
        "odrzucony nie kaskaduje dalej w sposób optymalizujący). Poniżej widać, że "
        "daje **gorszy i niestabilny** wynik."
    )
    st.plotly_chart(wykresy.wykres_porownania(pod_da, pod_naiwny), width="stretch")

    pary_da = znajdz_pary_blokujace(wynik.przydzial, miasto.kandydaci, miasto.oddzialy)
    pary_na = znajdz_pary_blokujace(naiwny, miasto.kandydaci, miasto.oddzialy)
    d1, d2 = st.columns(2)
    d1.metric(
        "Pary blokujące — deferred acceptance", len(pary_da),
        help="Para blokująca = kandydat wolałby inny oddział i miałby tam więcej punktów niż ostatni przyjęty. 0 = przydział stabilny.",
    )
    d2.metric("Pary blokujące — tryb naiwny", len(pary_na))
    if not pary_da and pary_na:
        st.success(
            "Deferred acceptance jest **stabilny** (0 par blokujących), a tryb naiwny "
            f"ma **{len(pary_na)}** par blokujących — to znaczy, że są kandydaci z "
            "wyższymi punktami odrzuceni na rzecz słabszych."
        )

    st.subheader("Końcowe progi punktowe per oddział")
    wiersze = []
    kand = {k.id: k for k in miasto.kandydaci}
    liczba_przyjetych = {o.id: 0 for o in miasto.oddzialy}
    for w in wynik.przydzial:
        if w.oddzial_id is not None:
            liczba_przyjetych[w.oddzial_id] += 1
    for o in miasto.oddzialy:
        prog = wynik.progi_koncowe.get(o.id)
        wiersze.append(
            {
                "Oddział": etykieta_oddzialu(miasto, o.id),
                "Limit": o.limit_miejsc,
                "Przyjęci": liczba_przyjetych[o.id],
                "Wolne miejsca": max(0, o.limit_miejsc - liczba_przyjetych[o.id]),
                "Próg punktowy": round(prog, 1) if prog is not None else None,
            }
        )
    df_progi = pd.DataFrame(wiersze).sort_values(
        "Próg punktowy", ascending=False, na_position="last"
    )
    st.dataframe(
        df_progi,
        width="stretch",
        hide_index=True,
        height=440,
        column_config={
            "Próg punktowy": st.column_config.NumberColumn(
                "Próg punktowy", format="%.1f", help="Pusty = niedobór chętnych (brak progu)."
            )
        },
    )

    with st.expander("Pełna tabela przydziału (wszyscy kandydaci)"):
        wiersze = []
        for w in wynik.przydzial:
            wiersze.append(
                {
                    "Kandydat": kand[w.kandydat_id].imie,
                    "Przydział": etykieta_oddzialu(miasto, w.oddzial_id) if w.oddzial_id is not None else "— niezakwalifikowany —",
                    "Numer preferencji": str(w.numer_preferencji + 1) if w.numer_preferencji is not None else "—",
                    "Punkty": f"{w.punkty:.1f}" if w.punkty is not None else "—",
                }
            )
        st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)


# ===========================================================================
# TAB 6 — Runda uzupełniająca (zaślepka)
# ===========================================================================

with tab6:
    st.header("Runda uzupełniająca — do implementacji")
    st.info(
        "**Zaślepka.** W realnej rekrutacji po ogłoszeniu list kandydaci **potwierdzają "
        "wolę** przyjęcia (składają oryginały świadectw). Ci, którzy tego nie zrobią, "
        "zwalniają miejsca, a wolne miejsca trafiają do **rundy uzupełniającej**."
    )
    st.markdown(
        """
        **Co obejmie ta zakładka po implementacji:**

        - symulacja odsetka kandydatów niepotwierdzających woli (parametr),
        - ponowne uruchomienie przydziału **na wolnych miejscach** dla
          niezakwalifikowanych kandydatów,
        - porównanie progów przed i po rundzie uzupełniającej.

        **Interfejs silnika jest już na to gotowy** — funkcja
        `rekrutacja.przydziel(...)` przyjmuje argument `zajete_miejsca`
        (mapa `oddzial_id → liczba zajętych miejsc`), więc rundę uzupełniającą
        da się dołożyć **bez przebudowy** rdzenia: wystarczy przekazać
        potwierdzone miejsca jako zajęte i pulę niezakwalifikowanych kandydatów.
        """
    )
    st.caption(
        "Sygnatura gotowa pod rozszerzenie: "
        "`przydziel(kandydaci, oddzialy, seed, zajete_miejsca=...)`."
    )
