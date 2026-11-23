"""Backtest de la règle « micro » (achat sur baisse, revente à la prochaine hausse).

Données journalières yfinance, 2 dernières années, AVEC frais de 1 $ par ordre.
Aucun ordre réel : ce script ne fait que lire des prix historiques.

    py -3.12 micro_backtest.py

Hypothèses (simples et prudentes) :
- On regarde seulement les prix de clôture (pas d'intrajournalier).
- Achat à la clôture du jour où le prix est >= X % sous le plus haut des
  N clôtures précédentes ; on prend d'abord la plus forte baisse.
- Vente à la clôture du premier jour où le gain atteint +Y %, la perte -Z %,
  ou après D jours de bourse. Ce qui reste ouvert à la fin est vendu (frais inclus).
- Titres US convertis en CAD avec CAD=X du même jour.
- Grille : choix des X/Y/Z sur la 1re année seulement, puis vérification sur
  la 2e année (que la grille n'a jamais vue).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

import micro_config as C


# ----------------------------------------------------------------------------
# Données
# ----------------------------------------------------------------------------
def load_prices_cad() -> pd.DataFrame:
    """Clôtures ajustées en CAD, une colonne par titre (NaN = pas de séance)."""
    tickers = list(dict.fromkeys(C.UNIVERSE + [C.BENCHMARK, C.FX_TICKER]))
    raw = yf.download(tickers, period="3y", interval="1d", auto_adjust=True,
                      progress=False, group_by="column", threads=False)["Close"]
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    raw = raw.sort_index()
    fx = raw[C.FX_TICKER].ffill().bfill()
    out = {}
    for sym in dict.fromkeys(C.UNIVERSE + [C.BENCHMARK]):
        s = raw[sym]
        out[sym] = s * fx if C.is_usd(sym) else s
    df = pd.DataFrame(out)
    return df.dropna(how="all")


# ----------------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------------
@dataclass
class Params:
    dip: float = C.DIP_PCT
    take_profit: float = C.TAKE_PROFIT_PCT
    stop_loss: float = C.STOP_LOSS_PCT
    lookback: int = C.LOOKBACK_DAYS
    max_hold: int = C.MAX_HOLD_DAYS

    def label(self) -> str:
        return (f"X={self.dip:g}% Y=+{self.take_profit:g}% Z=-{self.stop_loss:g}% "
                f"N={self.lookback} D={self.max_hold}")


def simulate(prices: pd.DataFrame, start, end, p: Params, fee: float) -> dict:
    syms = [s for s in C.UNIVERSE if s in prices.columns]
    # plus haut des N clôtures PRÉCÉDENTES, calculé sur les vraies séances du titre
    peaks = {}
    for s in syms:
        col = prices[s].dropna()
        peaks[s] = col.rolling(p.lookback).max().shift(1).reindex(prices.index)

    dates = prices.index[(prices.index > start) & (prices.index <= end)]
    cash = C.CAPITAL
    positions: dict[str, dict] = {}
    trades = []
    fees_paid = 0.0

    def sell(sym, i, price, reason):
        nonlocal cash, fees_paid
        pos = positions.pop(sym)
        proceeds = pos["shares"] * price - fee
        cash += proceeds
        fees_paid += fee
        trades.append({"symbole": sym, "achat": pos["date"], "vente": dates[i],
                       "pnl": proceeds - pos["cost"], "raison": reason})

    for i, d in enumerate(dates):
        row = prices.loc[d]
        # 1) ventes
        for sym in list(positions):
            price = row[sym]
            if pd.isna(price):
                continue
            pos = positions[sym]
            ret = price / pos["entry"] - 1
            if ret >= p.take_profit / 100:
                sell(sym, i, price, "objectif")
            elif ret <= -p.stop_loss / 100:
                sell(sym, i, price, "arret")
            elif i - pos["i"] >= p.max_hold:
                sell(sym, i, price, "duree")
        # 2) achats (plus forte baisse d'abord)
        cands = []
        for sym in syms:
            if sym in positions:
                continue
            price, peak = row[sym], peaks[sym].loc[d]
            if pd.isna(price) or pd.isna(peak):
                continue
            if price <= peak * (1 - p.dip / 100):
                cands.append((price / peak, sym, price))
        for _, sym, price in sorted(cands):
            if len(positions) >= C.MAX_POSITIONS:
                break
            spend = min(C.POSITION_SIZE, cash)
            if spend < C.MIN_ORDER + fee:
                break
            shares = (spend - fee) / price
            if not C.FRACTIONAL:
                shares = float(int(shares))
                spend = shares * price + fee
                if shares <= 0:
                    continue
            cash -= spend
            fees_paid += fee
            positions[sym] = {"shares": shares, "entry": price, "cost": spend,
                              "i": i, "date": d}

    # fin : on vend ce qui reste au dernier prix connu
    last = len(dates) - 1
    for sym in list(positions):
        price = prices[sym].loc[:dates[last]].dropna().iloc[-1]
        sell(sym, last, price, "fin")

    n = len(trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return {"trades": trades, "n": n, "wins": wins,
            "win_pct": 100 * wins / n if n else 0.0,
            "final": cash, "net": cash - C.CAPITAL, "fees": fees_paid,
            "ret_pct": 100 * (cash / C.CAPITAL - 1)}


def buy_and_hold(prices: pd.DataFrame, sym: str, start, end, fee: float) -> dict:
    s = prices[sym].dropna()
    s = s[(s.index > start) & (s.index <= end)]
    shares = (C.CAPITAL - fee) / s.iloc[0]
    final = shares * s.iloc[-1] - fee
    return {"final": final, "net": final - C.CAPITAL,
            "ret_pct": 100 * (final / C.CAPITAL - 1)}


# ----------------------------------------------------------------------------
# Affichage
# ----------------------------------------------------------------------------
def show(title: str, prices, start, end, p: Params) -> dict:
    r = simulate(prices, start, end, p, C.FEE_PER_ORDER)
    r0 = simulate(prices, start, end, p, 0.0)
    bh = buy_and_hold(prices, C.BENCHMARK, start, end, C.FEE_PER_ORDER)
    print(f"\n=== {title} ({start.date()} -> {end.date()}) ===")
    print(f"Règle : {p.label()}")
    print(f"  Trades                 : {r['n']}")
    print(f"  Gagnants               : {r['wins']} ({r['win_pct']:.0f} %)")
    print(f"  Frais payés            : {r['fees']:.2f} $")
    print(f"  Profit net (frais 1 $) : {r['net']:+.2f} $  ({r['ret_pct']:+.1f} %)")
    print(f"  Profit net si frais=0  : {r0['net']:+.2f} $  ({r0['ret_pct']:+.1f} %)")
    print(f"  Garder {C.BENCHMARK} (2 frais) : {bh['net']:+.2f} $  ({bh['ret_pct']:+.1f} %)")
    diff = r["net"] - bh["net"]
    print(f"  Règle vs {C.BENCHMARK}      : {diff:+.2f} $")
    return {"r": r, "r0": r0, "bh": bh}


def main() -> None:
    print("Téléchargement des prix (yfinance)...")
    prices = load_prices_cad()
    end = prices.index[-1]
    mid = end - pd.Timedelta(days=365)
    start = end - pd.Timedelta(days=730)
    print(f"Données : {prices.index[0].date()} -> {end.date()}, "
          f"{len(prices.columns)} titres, capital {C.CAPITAL:.0f} $, "
          f"frais {C.FEE_PER_ORDER:.2f} $/ordre, {C.MAX_POSITIONS} x {C.POSITION_SIZE:.0f} $")

    defaults = Params()
    show("Règle de micro_config.py sur 2 ans", prices, start, end, defaults)

    # --- grille : choix sur l'année 1 seulement ---
    print("\n=== Grille X/Y/Z : entraînement sur l'ANNÉE 1 seulement ===")
    results = []
    for x, y, z in itertools.product(C.GRID_DIP, C.GRID_TAKE_PROFIT, C.GRID_STOP_LOSS):
        p = Params(dip=x, take_profit=y, stop_loss=z)
        r = simulate(prices, start, mid, p, C.FEE_PER_ORDER)
        results.append((r["net"], -r["n"], p, r))
    results.sort(key=lambda t: (t[0], t[1]), reverse=True)
    print(f"{'règle':<42}{'trades':>7}{'gagn.%':>8}{'net $':>9}")
    for net, _, p, r in results[:8]:
        print(f"{p.label():<42}{r['n']:>7}{r['win_pct']:>8.0f}{net:>+9.2f}")
    print(f"... ({len(results)} combinaisons; la pire : "
          f"{results[-1][2].label()} -> {results[-1][0]:+.2f} $)")
    best = results[0][2]
    print(f"\nChoisie sur l'année 1 : {best.label()}")

    show("Année 1 (entraînement) - règle choisie", prices, start, mid, best)
    show("Année 2 (VÉRIFICATION, jamais vue) - règle choisie", prices, mid, end, best)

    print("\nRappel : 50 $ ne peuvent pas rapporter 1000 $/mois. Même +10 %/an = 5 $/an.")


if __name__ == "__main__":
    main()
