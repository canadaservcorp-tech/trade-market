"""Réglages du bot de PRATIQUE « micro » (argent fictif, aucun ordre réel).

Tout est ici : capital, frais, liste de titres et la règle d'achat/vente.
Ce fichier est indépendant de config.py (le bot réel) et ne l'importe pas.
"""

# --- Argent fictif -----------------------------------------------------------
CAPITAL = 50.00            # CAD de départ (fictifs)
MAX_POSITIONS = 2          # au plus 2 titres détenus en même temps
POSITION_SIZE = 25.00      # CAD par position, frais d'achat inclus
FEE_PER_ORDER = 1.00       # CAD par ordre (achat ET vente) ~ minimum IBKR Canada
MIN_ORDER = 5.00           # n'achète pas si moins de 5 $ disponibles
FRACTIONAL = True          # actions fractionnées simulées (0,137 action, etc.)

# --- Titres très liquides (TSX en CAD, US en USD converti en CAD) ------------
UNIVERSE = [
    "XIU.TO",   # iShares S&P/TSX 60
    "XIC.TO",   # iShares S&P/TSX Capped Composite
    "VFV.TO",   # Vanguard S&P 500 (CAD)
    "ZEB.TO",   # BMO Equal Weight Banks
    "XEQT.TO",  # iShares Core Equity ETF Portfolio
    "SPY",      # SPDR S&P 500
    "QQQ",      # Invesco Nasdaq 100
    "IWM",      # iShares Russell 2000
    "AAPL",     # Apple
    "MSFT",     # Microsoft
]
FX_TICKER = "CAD=X"        # yfinance : nombre de CAD pour 1 USD
BENCHMARK = "XEQT.TO"      # comparaison « acheter et garder »


def is_usd(symbol: str) -> bool:
    """Les titres sans suffixe .TO / .V sont cotés en USD."""
    return not symbol.upper().endswith((".TO", ".V", ".NE", ".CN"))


# --- La règle (fixe) ---------------------------------------------------------
# ACHAT : le prix est au moins DIP_PCT % sous le plus haut (clôtures) des
#         LOOKBACK_DAYS derniers jours de bourse.
# VENTE : +TAKE_PROFIT_PCT % (objectif) ou -STOP_LOSS_PCT % (arrêt de perte)
#         ou après MAX_HOLD_DAYS jours de bourse.
# Valeurs choisies par la grille de micro_backtest.py sur la 1re année
# seulement, puis vérifiées sur la 2e année (voir README-FR.md).
LOOKBACK_DAYS = 10         # N
DIP_PCT = 5.0              # X
TAKE_PROFIT_PCT = 8.0      # Y
STOP_LOSS_PCT = 8.0        # Z
MAX_HOLD_DAYS = 15         # D

# Petite grille testée par micro_backtest.py (N et D restent fixes)
GRID_DIP = [2.0, 3.0, 5.0]
GRID_TAKE_PROFIT = [2.0, 3.0, 5.0, 8.0]
GRID_STOP_LOSS = [3.0, 5.0, 8.0]

# --- Heures de marché (heure de Montréal) ------------------------------------
TIMEZONE = "America/Montreal"
MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)
