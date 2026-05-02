"""OpenAI client wrapper — traduction de titres et synthèse future."""
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
