# Tasks 005 — Notifications & Alertes

## État : EN ATTENTE (après spec-004)

### Telegram Service
- [ ] `backend/app/services/telegram.py` — TelegramNotifier complet
- [ ] `backend/app/services/telegram.py` — _format_signal_message (Markdown V2)
- [ ] `backend/app/services/telegram.py` — cooldown Redis
- [ ] `backend/app/services/telegram.py` — filtre heures silencieuses
- [ ] Intégration dans pipeline : signal_synthesizer publie → telegram envoie
- [ ] Tests : mock bot API → vérification format message

### Bot Commands
- [ ] `backend/app/services/telegram_commands.py` — handlers /status, /watchlist, /signal
- [ ] `backend/app/services/telegram_commands.py` — handlers /pause, /seuil
- [ ] Setup webhook ou polling selon config VPS

### Alert Configs
- [ ] Migration DB : table `alert_configs`
- [ ] `backend/app/routers/alerts.py` — CRUD alert configs
- [ ] Interface Settings → gestion alertes par actif
- [ ] Intégration seuils dans le pipeline de notification

### Tests & Vérification
- [ ] Test end-to-end : signal fort → notification Telegram reçue < 30s
- [ ] Test cooldown : pas de doublon sur 4h
- [ ] Test commandes bot : /signal MC.PA retourne signal correct
