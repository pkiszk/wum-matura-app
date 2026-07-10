"""Warstwa wizualizacji (Plotly) — oddzielona od rdzenia domenowego.

Buduje figury dla aplikacji Streamlit. Import Plotly żyje tylko tutaj i w
``app.py`` — pakiet ``rekrutacja`` pozostaje czystym Pythonem.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from rekrutacja import (
    Miasto,
    WynikSymulacji,
    punkty,
)

# Wspólna paleta.
KOLOR_PREF = {
    "1. wybór": "#2563eb",
    "2. wybór": "#16a34a",
    "3. wybór": "#d97706",
    "4.+ wybór": "#7c3aed",
    "niezakwalifikowani": "#dc2626",
    "poza (szuka)": "#94a3b8",
}


# ---------------------------------------------------------------------------
# Kategoryzacja stanu kandydata w danej rundzie (do Sankey i metryk)
# ---------------------------------------------------------------------------


def kubelek_preferencji(nr) -> str:
    if nr is None:
        return "niezakwalifikowani"
    if nr == 0:
        return "1. wybór"
    if nr == 1:
        return "2. wybór"
    if nr == 2:
        return "3. wybór"
    return "4.+ wybór"


def _stan_po_rundzie(miasto: Miasto, wynik: WynikSymulacji, r_idx: int) -> dict[int, str]:
    """Kubełek każdego kandydata po rundzie r_idx (0-based)."""
    kand = {k.id: k for k in miasto.kandydaci}
    runda = wynik.rundy[r_idx]
    stan: dict[int, str] = {}
    for k in miasto.kandydaci:
        oid = runda.przydzial.get(k.id)
        if oid is not None:
            stan[k.id] = kubelek_preferencji(runda.numer_preferencji.get(k.id, 0))
        else:
            # niezakwalifikowany definitywnie tylko jeśli wyczerpał listę do tej rundy
            # (heurystyka: brak przydziału i wszystkie preferencje już "przeszły")
            stan[k.id] = "poza (szuka)"
    # Ostatnia runda: wolni bez przydziału to definitywnie niezakwalifikowani.
    if r_idx == len(wynik.rundy) - 1:
        for k in miasto.kandydaci:
            if runda.przydzial.get(k.id) is None:
                stan[k.id] = "niezakwalifikowani"
    return stan


# ---------------------------------------------------------------------------
# Histogram punktów kandydatów (w oddziale ich 1. wyboru)
# ---------------------------------------------------------------------------


def histogram_punktow(miasto: Miasto) -> go.Figure:
    odd = miasto.oddzialy_wg_id
    wartosci = []
    for k in miasto.kandydaci:
        if k.preferencje:
            wartosci.append(punkty(k, odd[k.preferencje[0]]))
    fig = go.Figure(
        go.Histogram(x=wartosci, nbinsx=30, marker_color="#2563eb")
    )
    fig.update_layout(
        title="Rozkład punktów kandydatów (liczone dla oddziału 1. wyboru)",
        xaxis_title="punkty (0–200)",
        yaxis_title="liczba kandydatów",
        bargap=0.05,
        height=360,
        margin=dict(t=50, b=40, l=40, r=20),
    )
    fig.update_xaxes(range=[0, 200])
    return fig


# ---------------------------------------------------------------------------
# Rozkład długości list preferencji
# ---------------------------------------------------------------------------


def histogram_dlugosci_list(miasto: Miasto) -> go.Figure:
    dlugosci = [len(k.preferencje) for k in miasto.kandydaci]
    fig = go.Figure(go.Histogram(x=dlugosci, marker_color="#16a34a"))
    fig.update_layout(
        title="Rozkład długości list preferencji",
        xaxis_title="liczba oddziałów na liście",
        yaxis_title="liczba kandydatów",
        bargap=0.1,
        height=340,
        margin=dict(t=50, b=40, l=40, r=20),
    )
    return fig


# ---------------------------------------------------------------------------
# Popularność oddziałów (kandydaci na miejsce)
# ---------------------------------------------------------------------------


def wykres_popularnosci(
    miasto: Miasto, kandydaci_na_miejsce: dict[int, float], top: int = 25
) -> go.Figure:
    odd = miasto.oddzialy_wg_id
    szk = miasto.szkoly_wg_id
    pary = sorted(kandydaci_na_miejsce.items(), key=lambda x: x[1], reverse=True)[:top]
    etykiety = [
        f"{szk[odd[oid].szkola_id].nazwa} · {odd[oid].nazwa_profilu}" for oid, _ in pary
    ]
    wartosci = [round(v, 1) for _, v in pary]
    kolory = ["#dc2626" if v >= 1 else "#16a34a" for v in wartosci]
    fig = go.Figure(
        go.Bar(x=wartosci, y=etykiety, orientation="h", marker_color=kolory)
    )
    fig.update_layout(
        title=f"Popularność oddziałów — kandydaci na 1 miejsce (top {len(pary)})",
        xaxis_title="kandydaci / miejsce (chętni gdziekolwiek na liście)",
        height=max(360, 22 * len(pary)),
        margin=dict(t=50, b=40, l=10, r=20),
        yaxis=dict(autorange="reversed"),
    )
    fig.add_vline(x=1.0, line_dash="dash", line_color="#334155")
    return fig


# ---------------------------------------------------------------------------
# Sankey: przepływ między numerami preferencji między rundami
# ---------------------------------------------------------------------------


def sankey_przeplyw(miasto: Miasto, wynik: WynikSymulacji, r_idx: int) -> go.Figure:
    """Przepływ kandydatów między kubełkami preferencji z rundy r-1 do r."""
    kolejnosc = ["1. wybór", "2. wybór", "3. wybór", "4.+ wybór", "poza (szuka)", "niezakwalifikowani"]

    if r_idx == 0:
        stan_prev = {k.id: "poza (szuka)" for k in miasto.kandydaci}
    else:
        stan_prev = _stan_po_rundzie(miasto, wynik, r_idx - 1)
    stan_cur = _stan_po_rundzie(miasto, wynik, r_idx)

    # węzły: lewa strona (przed), prawa strona (po)
    labels = [f"przed: {b}" for b in kolejnosc] + [f"po: {b}" for b in kolejnosc]
    idx_prev = {b: i for i, b in enumerate(kolejnosc)}
    idx_cur = {b: i + len(kolejnosc) for i, b in enumerate(kolejnosc)}
    kolory_wezlow = [KOLOR_PREF[b] for b in kolejnosc] * 2

    przeplyw: dict[tuple[int, int], int] = {}
    for k in miasto.kandydaci:
        a = idx_prev[stan_prev[k.id]]
        b = idx_cur[stan_cur[k.id]]
        przeplyw[(a, b)] = przeplyw.get((a, b), 0) + 1

    src = [a for (a, b) in przeplyw]
    dst = [b for (a, b) in przeplyw]
    val = list(przeplyw.values())

    fig = go.Figure(
        go.Sankey(
            node=dict(
                label=labels,
                color=kolory_wezlow,
                pad=14,
                thickness=16,
                line=dict(color="rgba(0,0,0,0.2)", width=0.5),
            ),
            link=dict(source=src, target=dst, value=val),
        )
    )
    fig.update_layout(
        title=f"Przepływ kandydatów: runda {r_idx} → {r_idx + 1}",
        height=420,
        margin=dict(t=50, b=20, l=10, r=10),
        font=dict(size=12),
    )
    return fig


# ---------------------------------------------------------------------------
# Ewolucja progów punktowych wybranych oddziałów
# ---------------------------------------------------------------------------


def wykres_progow(
    miasto: Miasto, wynik: WynikSymulacji, oddzialy_ids: list[int]
) -> go.Figure:
    odd = miasto.oddzialy_wg_id
    szk = miasto.szkoly_wg_id
    fig = go.Figure()
    rundy_x = list(range(1, wynik.liczba_rund + 1))
    for oid in oddzialy_ids:
        y = []
        for runda in wynik.rundy:
            prog = runda.progi.get(oid)
            y.append(prog if prog is not None else None)
        etyk = f"{szk[odd[oid].szkola_id].nazwa} · {odd[oid].nazwa_profilu}"
        fig.add_trace(
            go.Scatter(
                x=rundy_x, y=y, mode="lines+markers", name=etyk, connectgaps=False
            )
        )
    fig.update_layout(
        title="Ewolucja progów punktowych po rundach",
        xaxis_title="runda",
        yaxis_title="próg (punkty ostatniego zakwalifikowanego)",
        height=420,
        margin=dict(t=50, b=40, l=40, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35),
    )
    return fig


# ---------------------------------------------------------------------------
# Porównanie DA vs naiwny — rozkład preferencji
# ---------------------------------------------------------------------------


def wykres_porownania(pod_da, pod_naiwny) -> go.Figure:
    kategorie = ["1. wybór", "2. wybór", "3. wybór", "4.+ wybór", "niezakwalifikowani"]

    def rozklad(pod):
        czworka_plus = sum(v for nr, v in pod.rozklad_preferencji.items() if nr >= 3)
        return [
            pod.rozklad_preferencji.get(0, 0),
            pod.rozklad_preferencji.get(1, 0),
            pod.rozklad_preferencji.get(2, 0),
            czworka_plus,
            pod.niezakwalifikowani,
        ]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Deferred acceptance", x=kategorie, y=rozklad(pod_da), marker_color="#2563eb"))
    fig.add_trace(go.Bar(name="Tryb naiwny", x=kategorie, y=rozklad(pod_naiwny), marker_color="#dc2626"))
    fig.update_layout(
        barmode="group",
        title="Porównanie: deferred acceptance vs tryb naiwny",
        yaxis_title="liczba kandydatów",
        height=400,
        margin=dict(t=50, b=40, l=40, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
    )
    return fig
