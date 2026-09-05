# Namatahvieh Telegram Growth & Sales Bot

Telegram bot for verified referrals, campaign tracking, AC lead qualification, home appliance leads, admin dashboard, CSV export, and privacy controls.

Runtime variables (Render deploy-bot branch, python webhook.py):
- BOT_TOKEN
- SETUP_SECRET
- BUSINESS_NAME=نما تهویه
- REWARD_POINTS=1
- SUPABASE_URL, SUPABASE_KEY, BOT_DB_SECRET
- WEBHOOK_URL, WEBHOOK_SECRET

First owner claim in Telegram:
`/claim <SETUP_SECRET>`

Then configure the channel:
`/setchannel @channelusername`

Customer entry points:
- `/start` welcomes the customer, clears unfinished forms, and shows a persistent chat button.
- `/chat` or the chat button exits a form and opens free questions; `/menu` opens sales services.
- Channel links use `?start=channel`, `?start=channel_quote`, and `?start=channel_callback`.
- The owner can use `/channel_panel` or `?start=channel_setup` to preview the welcome post.
  Only an owner click publishes/pins it; repeat clicks edit the same recorded message.
  The bot needs channel posting and editing permissions. Other pinned messages are preserved.
- Ordinary subscribers receive a private welcome only if they previously started the bot.
  Join requests use Telegram's short contact window; the bot does not approve requests or change admission rules.
- Private chat commands and the bot's welcome description are configured at startup.
- One small AI connectivity request runs per deployed revision and records only its status in config.

Checks: `python -m unittest -v test_channel_access` (mock Telegram, database, and AI; no network calls).
