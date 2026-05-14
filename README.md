# Hathway Agent

Standalone Telegram bot for **Hathway partners portal** only (multi/single STB audit, temp deactivate/activate, remove pack & terminate). English and Kannada UI.

## Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create `.env` in this folder (`hathway_agent/`) with at least:

   - `TELEGRAM_BOT_TOKEN=...`
   - `HATHWAY_USER` / `HATHWAY_PASS` (or `HATHWAY_ACCOUNTS_FILE` JSON — see `vk_agent/multi_credentials.py`)
   - Optional: `HATHWAY_LOGIN_URL` (defaults to the standard partners login URL)

3. Install dependencies and Playwright:

   ```bash
   cd hathway_agent
   pip install -r requirements.txt
   playwright install chromium
   ```

4. Install Tesseract OCR (same as your combined bot).

5. Run:

   ```bash
   python vk_agent/telegram_bot.py
   ```

Summarize logs:

```bash
python vk_agent/summarize_bot_request_log.py
```

## Publishing as its own GitHub repo

From `hathway_agent/`:

```bash
git init
git add .
git commit -m "Initial Hathway Agent"
git branch -M main
git remote add origin https://github.com/YOUR_USER/Hathway-Agent.git
git push -u origin main
```

Create the empty repository on GitHub first, then push.
