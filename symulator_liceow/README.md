# 🎓 Symulator rekrutacji do liceów

Edukacyjna aplikacja w Pythonie + Streamlit, która **krok po kroku** pokazuje,
jak z punktów kandydatów, list preferencji i limitów miejsc powstaje ostateczny
przydział do oddziałów (klas) w szkołach ponadpodstawowych — z iteracyjnym
przesuwaniem kandydatów między oddziałami.

Materiał wykładowy dla **rodziców i uczniów** bez przygotowania technicznego:
wizualizacje prowadzone są etapami, cała aplikacja i teksty są po polsku.

> Projekt jest **niezależny** od reszty tego repozytorium (aplikacji o progach na
> WUM). Żyje w całości w katalogu `symulator_liceow/` i można go uruchomić oraz
> replikować osobno.

## Szybki start

```bash
cd symulator_liceow
python -m venv .venv && source .venv/bin/activate     # opcjonalnie
pip install -r requirements.txt
streamlit run app.py
```

Aplikacja otworzy się w przeglądarce pod `http://localhost:8501`.

### Testy

```bash
cd symulator_liceow
pytest
```

## Co odwzorowuje model

Wiernie zaimplementowane polskie zasady rekrutacji (rozporządzenie MEN 2025,
ustawa *Prawo oświatowe*):

1. **Punktacja, maks. 200 pkt**, liczona **oddzielnie dla każdej pary
   (kandydat, oddział)**:
   - egzamin ósmoklasisty: polski ×0,35 + matematyka ×0,35 + język obcy ×0,30
     (maks. 100),
   - oceny z 4 przedmiotów (zawsze polski i matematyka + **dwa przedmioty
     punktowane zależne od oddziału**); przelicznik: celujący 18, bardzo dobry
     17, dobry 14, dostateczny 8, dopuszczający 2 (maks. 72),
   - świadectwo z wyróżnieniem +7, wolontariat +3, konkursy maks. +18.

   **Punkty tego samego kandydata różnią się między oddziałami** — to fundament
   modelu danych.

2. **Jednostką rekrutacji jest oddział** (profil klasy w konkretnej szkole) z
   własnym limitem miejsc i parą przedmiotów punktowanych. Kandydat składa jedną
   uporządkowaną listę preferencji; oddziały różnych szkół mogą się przeplatać.
   Limit liczby szkół na liście jest parametrem (domyślnie 3).

3. **Algorytm przydziału: deferred acceptance** (Gale-Shapley, student-proposing).
   Kandydat jest tymczasowo kwalifikowany do najwyższej preferencji, w której
   mieści się w limicie; wypchnięty przez kogoś z wyższą pozycją spada niżej i
   sam może wypychać innych. Iteracja do punktu stałego.

4. **Remisy**: ranking po punktach malejąco, a przy remisie tie-break
   leksykograficzny: (a) problemy zdrowotne kandydata, (b) kryteria ex aequo
   (wielodzietność, niepełnosprawności, samotne wychowywanie, piecza zastępcza),
   (c) losowanie z seedem.

5. **Wyjątki**: laureaci i finaliści olimpiad przyjmowani do 1. preferencji poza
   limitem punktowym. Gdy chętnych jest nie więcej niż miejsc — wchodzą wszyscy.

6. **Progów NIE zadaje się z góry** — próg oddziału to punkty ostatniego
   zakwalifikowanego i **wyłania się** z symulacji. Aplikacja pokazuje ewolucję
   progów po rundach.

## Struktura projektu

```
symulator_liceow/
├── app.py                    # aplikacja Streamlit (warstwa UI)
├── wykresy.py                # buildery wykresów Plotly (warstwa UI)
├── requirements.txt
├── README.md
├── rekrutacja/               # RDZEŃ DOMENOWY — czysty Python, bez Streamlit
│   ├── __init__.py
│   ├── modele.py             # dataclasses: Kandydat, Szkola, Oddzial, WynikPrzydzialu
│   ├── punktacja.py          # punkty(kandydat, oddzial) + rozbicie punktów
│   ├── matching.py           # deferred acceptance + tryb naiwny + stabilność
│   ├── generator.py          # generator danych syntetycznych ze seedem
│   └── analiza.py            # metryki podsumowujące
└── tests/
    └── test_rekrutacja.py    # testy własnościowe (pytest)
```

Rdzeń (`rekrutacja/`) jest **całkowicie oddzielony od UI** — nie importuje
Streamlita ani Plotly, więc silnik można używać z linii poleceń, w notatniku
albo w innej aplikacji.

## Zakładki aplikacji (sekwencja etapów)

1. **Miasto i kandydaci** — tabela szkół i oddziałów, histogram punktów, karta
   kandydata z wyliczeniem punktów do dwóch różnych oddziałów.
2. **Listy preferencji** — rozkład długości list, mapa popularności oddziałów.
3. **Listy rankingowe** — ranking wybranego oddziału z linią odcięcia na limicie.
4. **Symulacja krok po kroku** — nawigacja po rundach (poprzednia/następna +
   suwak), Sankey przepływu między preferencjami, wykres ewolucji progów,
   śledzenie wybranego kandydata.
5. **Wynik końcowy** — metryki, końcowe progi, porównanie z trybem naiwnym
   (dowód niestabilności: pary blokujące).
6. **Runda uzupełniająca** — zaślepka z opisem; interfejs silnika
   (`przydziel(..., zajete_miejsca=...)`) jest już przygotowany pod jej dodanie.

## Testy własnościowe

`tests/test_rekrutacja.py` sprawdza m.in.:

- **poprawność punktacji** na ręcznie policzonych przykładach,
- że **punkty zależą od oddziału**,
- **stabilność** matchingu (brak par blokujących) — także na ręcznym małym
  przypadku,
- **unikalność** przydziału i **determinizm** przy seedzie,
- że **tryb naiwny jest niestabilny** (ma pary blokujące), a deferred acceptance
  nie,
- wejście **olimpijczyka poza limitem** i regułę „wchodzą wszyscy” przy niedoborze.
