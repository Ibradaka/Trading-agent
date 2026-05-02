# Plan 005 — Notifications & Alertes

## Architecture Telegram

```python
# backend/app/services/telegram.py
from telegram import Bot
from telegram.constants import ParseMode

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def send_signal(self, signal: SignalOutput) -> None:
        if not self._should_notify(signal):
            return
        message = self._format_signal_message(signal)
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await self._record_notification(signal)

    def _should_notify(self, signal: SignalOutput) -> bool:
        # Filtre : score > threshold, pas en cooldown, pas en mode silencieux
        ...
```

## Cooldown Redis
```python
# Clé Redis : "notif:cooldown:{ticker}"
# TTL : 4h (configurable par actif)
# Bypass si signal opposé fort (score > 75 dans la direction inverse)
```

## Commandes bot (webhook ou polling)
```python
# Handlers python-telegram-bot
/start   → message bienvenue + aide
/status  → statut agents + DB + Redis
/watchlist → liste actifs avec signaux
/signal <ticker> → signal détaillé
/pause <ticker>  → toggle pause notifs
/seuil <ticker> <score> → modifier seuil
```

## Configuration alerts (DB)
```sql
-- Table alert_configs (à ajouter en migration)
CREATE TABLE alert_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),
    min_score INT DEFAULT 75,
    signal_types TEXT[] DEFAULT '{BUY,SELL}',
    notify_telegram BOOLEAN DEFAULT TRUE,
    is_paused BOOLEAN DEFAULT FALSE,
    quiet_hours_start TIME DEFAULT '20:00',
    quiet_hours_end TIME DEFAULT '08:00',
    cooldown_hours INT DEFAULT 4,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
