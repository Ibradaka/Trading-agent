from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    database_url: str
    postgres_password: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    @property
    def redis_url_with_auth(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@redis:6379/0"
        return self.redis_url

    # Data sources
    fred_api_key: str = ""
    alpha_vantage_key: str = ""

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    signal_alert_threshold: float = 0.70
    dashboard_url: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    default_refresh_minutes: int = 15
    market_open_cet: str = "09:00"
    market_close_cet: str = "17:30"
    max_active_assets: int = 30

    # CORS
    cors_origins: List[str] = ["http://localhost:5899", "http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
