"""OpenAI client wrapper — news translation, sentiment scoring, signal synthesis."""
import json
from openai import AsyncOpenAI
from app.config import settings
import structlog

logger = structlog.get_logger()
_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def score_sentiment_batch(ticker: str, titles: list[str]) -> list[float]:
    """
    Returns sentiment scores (-1 to +1) for each title via GPT-4o-mini.
    Falls back to [0.0, ...] if OpenAI is unavailable.
    """
    if not settings.openai_api_key or not titles:
        return [0.0] * len(titles)
    try:
        client = get_openai_client()
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un analyste sentiment financier. Pour chaque titre d'actualité, "
                        "donne un score entre -1 (très négatif pour l'action) et +1 (très positif). "
                        "Réponds UNIQUEMENT avec un tableau JSON de nombres flottants dans le même ordre. "
                        "Exemple: [-0.8, 0.3, 0, 0.9, -0.2]"
                    ),
                },
                {"role": "user", "content": f"Ticker: {ticker}\n\n{numbered}"},
            ],
            max_tokens=120,
            temperature=0.1,
        )
        content = resp.choices[0].message.content.strip()
        scores = json.loads(content)
        if isinstance(scores, list):
            return [max(-1.0, min(1.0, float(s))) for s in scores[: len(titles)]]
    except Exception as e:
        logger.warning("LLM sentiment scoring failed", ticker=ticker, error=str(e))
    return [0.0] * len(titles)


async def explain_signal(
    ticker: str,
    asset_name: str,
    fusion: dict,
    breakdown,
    indicators: dict,
    patterns: list[dict],
    sentiment_narrative: str = "",
    macro_narrative: str = "",
    macro_regime: str = "neutral",
    confidence: dict | None = None,
) -> dict | None:
    """
    Couche d'explication — le LLM ne décide pas, il explique une décision déjà prise.

    La décision (signal_type, fusion_score) vient du Signal Fusion Engine déterministe.
    Le LLM génère uniquement : reasoning, invalidation_conditions, horizon, risks.
    Retourne None si OpenAI est indisponible (fallback déterministe dans risk.py).
    """
    if not settings.openai_api_key:
        return None
    try:
        client = get_openai_client()

        bullish_pats = [p["pattern_name"] for p in patterns if p.get("direction") == "bullish"]
        bearish_pats = [p["pattern_name"] for p in patterns if p.get("direction") == "bearish"]

        rsi = indicators.get("rsi")
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        close = indicators.get("close")
        macd_hist = indicators.get("macd_histogram")

        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        ema20_str = f"{ema20:.2f}" if ema20 is not None else "N/A"
        ema50_str = f"{ema50:.2f}" if ema50 is not None else "N/A"
        macd_dir = "positif" if macd_hist and macd_hist > 0 else ("négatif" if macd_hist and macd_hist < 0 else "N/A")
        ema_trend = (
            "haussière" if all(v is not None for v in [close, ema20, ema50]) and close > ema20 > ema50
            else "baissière" if all(v is not None for v in [close, ema20, ema50]) and close < ema20 < ema50
            else "neutre"
        )
        conf_label = confidence["label"] if confidence else "medium"
        conf_reasons = ", ".join(confidence["reasons"][:2]) if confidence else ""

        context = (
            f"Ticker: {ticker} ({asset_name})\n"
            f"DÉCISION (déterministe) : {fusion['signal_type']} {fusion['signal_strength']}"
            f" — Fusion score: {fusion['score']:.0f}/100 — Confiance: {conf_label}\n\n"
            f"DÉCOMPOSITION DU SCORE DE FUSION :\n"
            f"- Technique composite (50%): {fusion['technical_composite']:.0f}/100\n"
            f"  → Technique {breakdown.technical:.0f} / Patterns {breakdown.patterns:.0f} / Momentum {breakdown.momentum:.0f}\n"
            f"- Sentiment (25%): {breakdown.sentiment:.0f}/100\n"
            f"- Macro (25%): {breakdown.macro:.0f}/100 — Régime: {macro_regime}\n\n"
            f"INDICATEURS CLÉS :\n"
            f"- RSI: {rsi_str} | MACD histogram: {macd_dir}\n"
            f"- Tendance EMA: {ema_trend} | EMA20: {ema20_str} | EMA50: {ema50_str}\n\n"
            f"PATTERNS :\n"
            f"- Haussiers: {', '.join(bullish_pats) or 'aucun'}\n"
            f"- Baissiers: {', '.join(bearish_pats) or 'aucun'}\n"
        )
        if sentiment_narrative:
            context += f"\nSENTIMENT: {sentiment_narrative}"
        if macro_narrative:
            context += f"\nMACRO: {macro_narrative}"
        if conf_reasons:
            context += f"\nCONFIANCE: {conf_reasons}"

        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un analyste swing trading senior. "
                        "La décision d'achat/vente EST DÉJÀ PRISE de façon déterministe. "
                        "Ton rôle est UNIQUEMENT d'expliquer pourquoi cette décision est justifiée "
                        "et d'identifier les risques. Sois factuel, concis, en français. "
                        "Réponds UNIQUEMENT en JSON valide avec les champs: "
                        "reasoning (string, 2-3 phrases max), "
                        "invalidation_conditions (string, 1 phrase), "
                        "horizon (string), "
                        "risks (array de strings, max 3)."
                    ),
                },
                {"role": "user", "content": context},
            ],
            max_tokens=500,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        result = json.loads(resp.choices[0].message.content)
        return {
            "reasoning": result.get("reasoning", ""),
            "invalidation_conditions": result.get("invalidation_conditions", ""),
            "horizon": result.get("horizon", "3-10 jours (swing trading)"),
            "risks": result.get("risks", []),
            "llm_raw_output": result,
        }
    except Exception as e:
        logger.warning("LLM explain_signal failed", ticker=ticker, error=str(e))
        return None


async def translate_titles_to_french(titles: list[str]) -> list[str]:
    """Traduit une liste de titres en français via GPT-4o-mini (appel groupé)."""
    if not settings.openai_api_key or not titles:
        return titles
    try:
        client = get_openai_client()
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un traducteur financier. Traduis ces titres de news en français. "
                        "Réponds uniquement avec les titres numérotés traduits, un par ligne. "
                        "Conserve les noms propres, tickers boursiers et termes financiers spécialisés."
                    ),
                },
                {"role": "user", "content": numbered},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        lines = resp.choices[0].message.content.strip().split("\n")
        result = []
        for i, original in enumerate(titles):
            if i < len(lines):
                line = lines[i].strip()
                if line and ". " in line and line[0].isdigit():
                    line = line.split(". ", 1)[1]
                result.append(line or original)
            else:
                result.append(original)
        return result
    except Exception as e:
        logger.warning("LLM translation failed", error=str(e))
        return titles
