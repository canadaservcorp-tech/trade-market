"""Bot de PRATIQUE « micro » : argent fictif, AUCUN ordre réel.

Une exécution = lire les prix actuels (yfinance), appliquer la règle de
micro_config.py, écrire les achats/ventes fictifs dans paper_micro.csv et
l'état dans paper_state.json (dans ce dossier).

    py -3.12 micro_paper.py            une passe (hors des heures de marché : rien)
    py -3.12 micro_paper.py --force    une passe même hors des heures de marché
    py -3.12 micro_paper.py --rapport  solde, profit net après frais, liste des trades

Pour repartir à zéro : supprimer paper_state.json et paper_micro.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import micro_config as C

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "paper_state.json"
TRADES_FILE = HERE / "paper_micro.csv"
LOG_FILE = HERE / "micro_paper.log"
CSV_FIELDS = ["date_heure", "action", "symbole", "prix_cad", "quantite",
              "montant_cad", "frais_cad", "profit_net_cad", "raison", "cash_apres"]


def now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=C.TIMEZONE)


def log(msg: str) -> None:
    line = f"{now():%Y-%m-%d %H:%M} {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ----------------------------------------------------------------------------
# État
# ----------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"cash": C.CAPITAL, "positions": {}, "fees_paid": 0.0,
            "created": now().isoformat(timespec="minutes")}


def save_state(state: dict) -> None:
    state["updated"] = now().isoformat(timespec="minutes")
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def record(row: dict) -> None:
    new = not TRADES_FILE.exists()
    with TRADES_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


# ----------------------------------------------------------------------------
# Prix (yfinance seulement)
# ----------------------------------------------------------------------------
def fetch_market(symbols: list[str]) -> tuple[dict, dict]:
    """Retourne (prix actuel en CAD, plus haut des N clôtures précédentes en CAD)."""
    tickers = list(dict.fromkeys(symbols + [C.FX_TICKER]))
    hist = yf.download(tickers, period="2mo", interval="1d", auto_adjust=True,
                       progress=False, group_by="column", threads=False)["Close"]
    hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
    today = pd.Timestamp(now().date())

    def current(sym: str) -> float | None:
        try:
            v = yf.Ticker(sym).fast_info["last_price"]
            if v and np.isfinite(v):
                return float(v)
        except Exception:
            pass
        col = hist[sym].dropna() if sym in hist else pd.Series(dtype=float)
        return float(col.iloc[-1]) if len(col) else None

    fx = current(C.FX_TICKER)
    if not fx:
        raise RuntimeError("Taux CAD=X introuvable")
    prices, peaks = {}, {}
    for sym in symbols:
        px = current(sym)
        if px is None:
            continue
        rate = fx if C.is_usd(sym) else 1.0
        prices[sym] = px * rate
        past = hist[sym].dropna()
        past = past[past.index < today].tail(C.LOOKBACK_DAYS)
        if len(past) == C.LOOKBACK_DAYS:
            # approximation : le plus haut passé converti au taux du jour
            peaks[sym] = float(past.max()) * rate
    return prices, peaks


# ----------------------------------------------------------------------------
# Une passe
# ----------------------------------------------------------------------------
def market_open(t: pd.Timestamp) -> bool:
    if t.weekday() >= 5:
        return False
    hm = (t.hour, t.minute)
    return C.MARKET_OPEN <= hm <= C.MARKET_CLOSE


def run_once(force: bool) -> None:
    t = now()
    if not force and not market_open(t):
        log("Marché fermé (heure de Montréal) : rien à faire. --force pour forcer.")
        return
    state = load_state()
    fee = C.FEE_PER_ORDER
    stamp = t.strftime("%Y-%m-%d %H:%M")
    prices, peaks = fetch_market(C.UNIVERSE)

    # 1) ventes
    for sym, pos in list(state["positions"].items()):
        price = prices.get(sym)
        if price is None:
            log(f"{sym}: prix indisponible, position gardée")
            continue
        ret = price / pos["entry_price"] - 1
        held = int(np.busday_count(pos["entry_date"], t.date().isoformat()))
        reason = None
        if ret >= C.TAKE_PROFIT_PCT / 100:
            reason = f"objectif +{C.TAKE_PROFIT_PCT:g}%"
        elif ret <= -C.STOP_LOSS_PCT / 100:
            reason = f"arret -{C.STOP_LOSS_PCT:g}%"
        elif held >= C.MAX_HOLD_DAYS:
            reason = f"duree {held} j"
        if reason is None:
            log(f"{sym}: garde ({ret * 100:+.2f} %, {held} j)")
            continue
        gross = pos["shares"] * price
        proceeds = gross - fee
        pnl = proceeds - pos["cost"]
        state["cash"] += proceeds
        state["fees_paid"] += fee
        del state["positions"][sym]
        record({"date_heure": stamp, "action": "VENTE", "symbole": sym,
                "prix_cad": f"{price:.4f}", "quantite": f"{pos['shares']:.6f}",
                "montant_cad": f"{gross:.2f}", "frais_cad": f"{fee:.2f}",
                "profit_net_cad": f"{pnl:+.2f}", "raison": reason,
                "cash_apres": f"{state['cash']:.2f}"})
        log(f"VENTE fictive {sym} @ {price:.2f} $CA ({reason}) profit net {pnl:+.2f} $")

    # 2) achats : plus forte baisse d'abord
    cands = []
    for sym, price in prices.items():
        peak = peaks.get(sym)
        if sym in state["positions"] or peak is None:
            continue
        if price <= peak * (1 - C.DIP_PCT / 100):
            cands.append((price / peak, sym, price))
    for ratio, sym, price in sorted(cands):
        if len(state["positions"]) >= C.MAX_POSITIONS:
            break
        spend = min(C.POSITION_SIZE, state["cash"])
        if spend < C.MIN_ORDER + fee:
            break
        shares = (spend - fee) / price
        if not C.FRACTIONAL:
            shares = float(int(shares))
            if shares <= 0:
                continue
            spend = shares * price + fee
        state["cash"] -= spend
        state["fees_paid"] += fee
        state["positions"][sym] = {"shares": shares, "entry_price": price,
                                   "cost": spend, "entry_date": t.date().isoformat()}
        record({"date_heure": stamp, "action": "ACHAT", "symbole": sym,
                "prix_cad": f"{price:.4f}", "quantite": f"{shares:.6f}",
                "montant_cad": f"{spend - fee:.2f}", "frais_cad": f"{fee:.2f}",
                "profit_net_cad": "", "raison": f"{(1 - ratio) * 100:.1f}% sous le haut {C.LOOKBACK_DAYS} j",
                "cash_apres": f"{state['cash']:.2f}"})
        log(f"ACHAT fictif {sym} @ {price:.2f} $CA ({(1 - ratio) * 100:.1f} % sous le haut)")

    if not cands:
        dips = sorted(((1 - prices[s] / peaks[s]) * 100, s) for s in prices if s in peaks)
        top = ", ".join(f"{s} {d:+.1f}%" for d, s in sorted(dips, reverse=True)[:3])
        log(f"Aucun signal d'achat (seuil {C.DIP_PCT:g} %). Plus fortes baisses : {top}")
    save_state(state)
    log(f"Cash fictif : {state['cash']:.2f} $, positions : {list(state['positions']) or 'aucune'}")


# ----------------------------------------------------------------------------
# Rapport
# ----------------------------------------------------------------------------
def report() -> None:
    state = load_state()
    print("=== RAPPORT — bot de pratique micro (argent FICTIF) ===")
    print(f"Capital de départ : {C.CAPITAL:.2f} $")
    print(f"Cash              : {state['cash']:.2f} $")
    value = 0.0
    if state["positions"]:
        prices, _ = fetch_market(list(state["positions"]))
        print("Positions ouvertes :")
        for sym, pos in state["positions"].items():
            px = prices.get(sym, pos["entry_price"])
            v = pos["shares"] * px
            value += v
            print(f"  {sym:<8} {pos['shares']:.4f} @ {pos['entry_price']:.2f} -> {px:.2f} $"
                  f"  valeur {v:.2f} $ ({(px / pos['entry_price'] - 1) * 100:+.2f} %)"
                  f"  depuis {pos['entry_date']}")
    else:
        print("Positions ouvertes : aucune")
    sell_fees = C.FEE_PER_ORDER * len(state["positions"])
    equity = state["cash"] + value - sell_fees
    print(f"Valeur si on vendait tout maintenant (frais inclus) : {equity:.2f} $")
    print(f"PROFIT NET après frais : {equity - C.CAPITAL:+.2f} $ "
          f"({(equity / C.CAPITAL - 1) * 100:+.2f} %)")
    print(f"Frais payés jusqu'ici   : {state['fees_paid']:.2f} $")

    print("\nTrades :")
    if not TRADES_FILE.exists():
        print("  (aucun)")
        return
    with TRADES_FILE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        pnl = f"  net {r['profit_net_cad']} $" if r["profit_net_cad"] else ""
        print(f"  {r['date_heure']}  {r['action']:<5} {r['symbole']:<8} @ {float(r['prix_cad']):.2f} $"
              f"  montant {r['montant_cad']} $  frais {r['frais_cad']} $ {pnl}  ({r['raison']})")
    sells = [r for r in rows if r["action"] == "VENTE"]
    if sells:
        wins = sum(1 for r in sells if float(r["profit_net_cad"]) > 0)
        print(f"\nVentes : {len(sells)}, gagnantes : {wins} ({100 * wins / len(sells):.0f} %)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Bot de pratique micro (argent fictif)")
    ap.add_argument("--rapport", action="store_true", help="afficher le rapport")
    ap.add_argument("--force", action="store_true", help="ignorer les heures de marché")
    args = ap.parse_args()
    if args.rapport:
        report()
    else:
        run_once(args.force)


if __name__ == "__main__":
    main()
