# Spec 005 — Notifications & Alertes

## Objectif
Système de notifications Telegram avec formatting riche.
Alertes configurables par actif et par type de signal.

## Critères d'acceptation

- [ ] Notification Telegram envoyée < 30s après un signal fort (score > 75)
- [ ] Message Telegram avec formatting : score, signal, reasoning, risques
- [ ] Pas de spam : cooldown 4h entre deux notifications sur le même actif (sauf signal opposé fort)
- [ ] Mode silencieux configurable (heures calmes : 20h-8h)
- [ ] Commandes Telegram : /status, /watchlist, /signal [ticker]
- [ ] Alertes configurables : seuil par actif, types de signal voulus

## Format message Telegram

```
📈 SIGNAL BUY FORT — MC.PA (LVMH)

Score : 78/100 | Confiance : 82%
Horizon : 5-10 jours

🎯 Raisonnement :
RSI sortant de survente (28→35), MACD croisement haussier,
EMA20 > EMA50, sentiment positif secteur luxe.

⚠️ Risques :
• Résistance à 720€
• Publication résultats vendredi

🛑 Invalidation : Clôture sous 695€

📊 Breakdown :
Technique: 72 | Patterns: 65 | Momentum: 80 | Macro: 70 | Sentiment: 60

⏱ Analysé il y a 2 min
```

## Commandes bot

- `/status` → statut des agents + dernière MAJ
- `/watchlist` → liste des actifs avec signaux courants
- `/signal MC.PA` → signal détaillé pour un actif
- `/pause MC.PA` → pause notifications pour cet actif
- `/seuil MC.PA 80` → changer le seuil d'alerte
