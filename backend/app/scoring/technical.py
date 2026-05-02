"""
Scoring technique (0-100) et momentum (0-100) à partir des indicateurs pandas-ta.

Formule technique (spec-002) :
  MACD         ±20 pts  (croisement + position par rapport à ligne signal)
  RSI          ±25 pts  (survente / surachat / neutre)
  EMA alignment +20 pts  (price > ema20 > ema50 > ema200 = tendance propre)
  Bollinger    ±15 pts  (position du prix dans les bandes)
  Volume        +10 pts  (confirmation par volume)
  Stochastique ±10 pts
  Base = 50, normalisation : max(0, min(100, base + points))

Formule momentum (séparée) :
  RSI          ±30 pts
  MACD hist    ±20 pts
  Williams %R  ±25 pts
  Stochastique ±25 pts
  Base = 50, normalisation identique
"""


def compute_technical_score(ind: dict) -> float:
    """
    ind : dict issu de technical._compute_indicators_sync
    Retourne un score 0-100 axé sur la tendance.
    """
    points = 0.0

    # --- MACD (±20 pts) ---
    macd_hist = ind.get("macd_histogram")
    prev_macd_hist = ind.get("prev_macd_histogram")
    if macd_hist is not None:
        points += 10.0 if macd_hist > 0 else -10.0
        if prev_macd_hist is not None:
            if prev_macd_hist < 0 < macd_hist:
                points += 10.0   # croisement haussier
            elif prev_macd_hist > 0 > macd_hist:
                points -= 10.0   # croisement baissier

    # --- RSI (±25 pts) ---
    rsi = ind.get("rsi")
    if rsi is not None:
        if rsi < 30:
            points += 25.0
        elif rsi < 40:
            points += 15.0
        elif rsi < 50:
            points += 5.0
        elif rsi < 60:
            points -= 5.0
        elif rsi < 70:
            points -= 15.0
        else:
            points -= 25.0

    # --- EMA Alignment (+20 pts) ---
    ema20 = ind.get("ema20")
    ema50 = ind.get("ema50")
    ema200 = ind.get("ema200")
    close = ind.get("close")
    if all(v is not None for v in [ema20, ema50, ema200, close]):
        if close > ema20 > ema50 > ema200:
            points += 20.0
        elif close < ema20 < ema50 < ema200:
            points -= 20.0
        elif ema20 > ema50 > ema200:
            points += 10.0
        elif ema20 < ema50 < ema200:
            points -= 10.0

    # --- Bollinger Bands (±15 pts) ---
    bb_upper = ind.get("bb_upper")
    bb_lower = ind.get("bb_lower")
    if all(v is not None for v in [bb_upper, bb_lower, close]):
        band_width = bb_upper - bb_lower
        if band_width > 0:
            position = (close - bb_lower) / band_width
            if position < 0.10:
                points += 15.0
            elif position < 0.25:
                points += 8.0
            elif position > 0.90:
                points -= 15.0
            elif position > 0.75:
                points -= 8.0

    # --- Volume (±10 pts) ---
    volume = ind.get("volume")
    volume_ma20 = ind.get("volume_ma20")
    if volume is not None and volume_ma20 and volume_ma20 > 0:
        ratio = volume / volume_ma20
        if ratio > 1.5:
            points += 10.0
        elif ratio > 1.2:
            points += 5.0
        elif ratio < 0.5:
            points -= 5.0

    # --- Stochastique (±10 pts) ---
    stoch_k = ind.get("stoch_k")
    stoch_d = ind.get("stoch_d")
    prev_stoch_k = ind.get("prev_stoch_k")
    if stoch_k is not None:
        if stoch_k < 20:
            points += 10.0
        elif stoch_k < 30:
            points += 5.0
        elif stoch_k > 80:
            points -= 10.0
        elif stoch_k > 70:
            points -= 5.0
        if stoch_d is not None and prev_stoch_k is not None:
            if prev_stoch_k < stoch_d < stoch_k:
                points += 3.0   # croisement haussier K/D

    return max(0.0, min(100.0, 50.0 + points))


def compute_momentum_score(ind: dict) -> float:
    """
    Score momentum (0-100) axé sur les oscillateurs.
    Distinct du technical_score pour alimenter le composant momentum (20%)
    du score composite.
    """
    points = 0.0

    # --- RSI (±30 pts) ---
    rsi = ind.get("rsi")
    if rsi is not None:
        if rsi < 25:
            points += 30.0
        elif rsi < 35:
            points += 18.0
        elif rsi < 45:
            points += 6.0
        elif rsi < 55:
            points -= 0.0   # zone neutre
        elif rsi < 65:
            points -= 6.0
        elif rsi < 75:
            points -= 18.0
        else:
            points -= 30.0

    # --- MACD histogram (±20 pts) ---
    macd_hist = ind.get("macd_histogram")
    macd_val = ind.get("macd")
    macd_sig = ind.get("macd_signal")
    if macd_hist is not None:
        if macd_hist > 0:
            points += 10.0
        else:
            points -= 10.0
        prev = ind.get("prev_macd_histogram")
        if prev is not None:
            if prev < 0 < macd_hist:
                points += 10.0
            elif prev > 0 > macd_hist:
                points -= 10.0

    # --- Williams %R (±25 pts) ---
    willr = ind.get("williams_r")
    if willr is not None:
        if willr < -80:
            points += 25.0
        elif willr < -60:
            points += 12.0
        elif willr > -20:
            points -= 25.0
        elif willr > -40:
            points -= 12.0

    # --- Stochastique (±25 pts) ---
    stoch_k = ind.get("stoch_k")
    if stoch_k is not None:
        if stoch_k < 15:
            points += 25.0
        elif stoch_k < 25:
            points += 12.0
        elif stoch_k > 85:
            points -= 25.0
        elif stoch_k > 75:
            points -= 12.0

    return max(0.0, min(100.0, 50.0 + points))
