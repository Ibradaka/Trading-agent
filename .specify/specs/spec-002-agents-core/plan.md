# Plan 002 — Agents Core (Déterministes)

## Ordre d'implémentation

```
1. Watchlist Manager  (J1)  — base de toute la pipeline
2. Market Data Agent  (J2)  — données brutes
3. Technical Analysis (J3)  — indicateurs
4. Pattern Detection  (J4)  — figures chartistes
5. Risk/Confidence    (J4)  — filtres + confiance
6. Tests unitaires    (J5)  — couverture complète scoring
```

## Watchlist Manager

### Validation ticker
```python
async def validate_ticker(ticker: str) -> TickerValidation:
    info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
    # Checks: regularMarketPrice non null, volume > 0
    # Détecte type: equity/commodity/index/crypto/forex
    # Détermine éligibilité PEA via exchange suffix
    # Retourne métadonnées enrichies
```

### Détection type d'actif
- `=F` suffix → commodity (futures)
- `^` prefix → index
- `-USD` ou `-EUR` suffix → crypto
- `=X` suffix → forex
- Exchange in [ENX, PAR, AMS, BRU, LIS, XETRA, MIL, MAD] → equity PEA éligible
- Sinon → equity non-PEA

### API endpoints
```
POST /api/assets/validate?ticker=MC.PA     → validation + métadonnées
POST /api/watchlists/{id}/assets           → add asset to watchlist
DELETE /api/watchlists/{id}/assets/{ticker}
PATCH /api/watchlists/{id}/assets/{ticker} → notes, target prices, pause
```

## Market Data Agent

### Fetch stratégie
```python
async def fetch_ohlc(ticker: str, period: str = "6mo", interval: str = "1d"):
    # asyncio.to_thread pour yfinance (synchrone)
    # Normalise les colonnes
    # Vérifie intégrité (pas de gaps > 5j ouvrés)
    # Écrit dans TimescaleDB avec ON CONFLICT DO UPDATE
    # Publie sur Redis: "data:updated:{ticker}"
```

### Refresh scheduler
- Toutes les 15 min pendant heures marché (09h-17h30 CET)
- `exchange_calendars.get_calendar("XPAR")` pour Euronext Paris
- `exchange_calendars.get_calendar("XETR")` pour Xetra
- Batch : max 10 tickers en parallèle (asyncio.gather)

## Technical Analysis Agent

### Indicateurs calculés (pandas-ta)
```python
df.ta.macd(fast=12, slow=26, signal=9)       # MACD, Signal, Histogram
df.ta.rsi(length=14)                          # RSI
df.ta.ema(length=20)                          # EMA 20
df.ta.ema(length=50)                          # EMA 50
df.ta.ema(length=200)                         # EMA 200
df.ta.sma(length=20)                          # SMA 20
df.ta.sma(length=50)                          # SMA 50
df.ta.bbands(length=20, std=2)                # Bollinger Bands
df.ta.atr(length=14)                          # ATR
df.ta.obv()                                   # OBV
df.ta.stoch(k=14, d=3)                        # Stochastique
df.ta.adx(length=14)                          # ADX
df.ta.willr(length=14)                        # Williams %R
```

### Signaux atomiques
```python
{
    "macd_cross_up": bool,    # MACD croise au-dessus du signal
    "macd_cross_down": bool,
    "rsi": float,
    "rsi_oversold": bool,     # RSI < 30
    "rsi_overbought": bool,   # RSI > 70
    "rsi_rising": bool,       # RSI en hausse vs 3 bougies précédentes
    "ema_alignment_bullish": bool,  # ema20 > ema50 > ema200
    "price_above_ema200": bool,
    "bb_squeeze": bool,       # Bollinger < 75% de sa moyenne historique
    "price_near_bb_lower": bool,  # prix < bb_lower + 0.5*ATR
    "volume_surge": bool,     # volume > 1.5x moyenne 20j
    "stoch_cross_up": bool,   # stoch K croise D vers le haut
    "adx_trending": bool,     # ADX > 25
}
```

## Pattern Detection Agent

### Chandeliers (via pandas-ta CDL functions)
Détecte : Engulfing (haussier/baissier), Doji, Hammer, Shooting Star, Morning/Evening Star,
Three White Soldiers/Black Crows, Harami, Piercing Line, Dark Cloud Cover, Marubozu

### Figures chartistes (custom)
- Double Bottom / Double Top (fenêtre 60j, tolérance 2%)
- Head & Shoulders / Inverse H&S (fenêtre 90j)
- Triangle ascendant / descendant / symétrique (fenêtre 30j)
- Support / Résistance dynamiques (pivots sur 20j)

## Risk/Confidence Agent

### Filtres déterministes
```python
FILTERS = [
    volume_filter,          # volume > avg_20d / 2
    volatility_filter,      # ATR/prix < 5% (pas en régime chaotique)
    liquidity_filter,       # pas de gap > 3% sans news
    cooldown_filter,        # pas de signal opposé < 48h
    multiframe_filter,      # cohérence daily vs 4H
]
```

### Calcul confiance
```python
confidence = (
    signal_consistency * 0.40 +  # indicateurs convergents
    volume_confirmation * 0.30 +  # volume confirme direction
    pattern_strength * 0.20 +    # force du pattern
    macro_alignment * 0.10       # contexte macro favorable
)
```
