# SC Log Monitor

A lightweight Windows system-tray app that watches the Star Citizen `Game.log` in real time and detects blueprint drops. It works fully **standalone** — all blueprints are saved locally to a JSON file you can browse any time. Optionally, pair it with the [Star Citizen Blueprint Bot](https://github.com/city028/sc-blueprint-bot) to automatically sync your blueprints to Discord and share them with your organisation.

---

## Download & Install

1. Go to the [Releases page](https://github.com/city028/sc-log-monitor/releases/latest)
2. Download `SC-Log-Monitor.exe`
3. Place it anywhere — Desktop, a dedicated folder, wherever you prefer
4. Double-click to run — no installation required
5. On first run, a config file is created automatically at `%LOCALAPPDATA%\SC Log Monitor\config.ini`

> Discord integration is **optional** — the app works fully standalone without it.

---

## Features

- Detects blueprint drop notifications from `Game.log` in real time
- Appends each blueprint to a single persistent `blueprints.json` file — your local record of every blueprint you own
- Backs up `blueprints.json` before every write (configurable max backups)
- Works fully **standalone** — no Discord account or bot required
- **Optional Discord sync** — pair with the Star Citizen Blueprint Bot to upload blueprints automatically and share them with your organisation
- System tray icon with live session count and link status
- Starts with Windows (configurable)
- All settings configurable via an in-app Settings dialog — no manual file editing

---

## Standalone use (no Discord)

Just download, run, and play. The app will:

- Watch your `Game.log` for blueprint drops
- Save each blueprint with a timestamp to `Documents\Blueprints\blueprints.json`
- Show a live count in the system tray tooltip

No Discord setup needed. The Discord tab in Settings can be left blank.

---

## Optional: Discord sync

If you want your blueprints automatically synced to a Discord server (and visible to your org), you can pair the app with the **Star Citizen Blueprint Bot**.

- [Blueprint Bot GitHub](https://github.com/city028/sc-blueprint-bot)
- [Support Discord](https://discord.com/invite/m5uPvRWq5t)
- [Install the bot on your server](https://discord.com/oauth2/authorize?client_id=1493936820143259720)

Once the bot is set up in your Discord server, see [First-time Discord setup](#first-time-discord-setup) below.

---

## Requirements (running from source)

> Skip this section if you downloaded `SC-Log-Monitor.exe` from the Releases page.

- Python 3.11+
- Install dependencies: `pip install -r requirements.txt`

```
pystray==0.19.5
Pillow==12.2.0
requests>=2.31.0
```

Run with: `python sc_log_monitor.py` or `launch.vbs` (suppresses the console window).

Config is stored at `%LOCALAPPDATA%\SC Log Monitor\config.ini` in both the `.exe` and source modes.

---

## Configuration

All settings are stored in `config.ini` and editable via the Settings dialog.

### General tab

| Setting | Description | Default |
|---------|-------------|---------|
| Game log file | Path to Star Citizen `Game.log` | `C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log` |
| Output directory | Where `blueprints.json` is written | `Documents\Blueprints` |
| Backup directory | Where timestamped backups are stored | `Documents\Blueprints\bak` |
| Max backups | How many backup files to keep | `10` |
| Poll interval | How often to check the log (seconds) | `1.0` |
| Start with Windows | Register app to launch at login | Enabled (when running as .exe) |

### Discord tab

> All fields are optional. Leave blank to use the app in standalone mode.

| Setting | Source | Description |
|---------|--------|-------------|
| Webhook URL | Guild admin | Channel webhook URL for posting blueprint embeds |
| Guild Token | Guild admin | Per-guild security token included in every embed |
| Link Token | `/blueprint-link` command | One-time token — enter and click **Link Account** to pair |
| Discord User ID | Auto-populated | Your Discord snowflake ID, resolved during the link handshake |

> **Security note:** Webhook URL and Guild Token are provided by your server administrator. Do not share them publicly.

---

## First-time Discord setup

1. Obtain the **Webhook URL** and **Guild Token** from your server administrator
2. Open tray → **Settings** → **Discord** tab
3. Fill in Webhook URL and Guild Token
4. In your Discord server run `/blueprint-link` — the bot responds with a one-time token
5. Paste the token into **Link Token** and click **Link Account**
6. Within ~60 seconds **Discord User ID** will populate automatically
7. Click **Save** — the app is now paired and ready to send blueprint embeds

> If you need to re-pair (e.g. moving to a new guild), click **Reset Discord Settings** (red button) to clear all credentials, then repeat from step 1.

---

## blueprints.json format

```json
[
  {
    "item": "Citadel",
    "timestamp": "2026-06-30T10:16:33Z"
  },
  {
    "item": "Defiant",
    "timestamp": "2026-07-02T06:04:31Z"
  }
]
```

A flat list — one entry per blueprint, ordered by detection time. Grows indefinitely across all sessions.

---

## Tray menu

| Item | Action |
|------|--------|
| Settings | Opens the settings dialog |
| Sync to Discord | Resends all `blueprints.json` entries as individual Discord embeds |
| Open Output Folder | Opens the output directory in Explorer |
| Quit | Exits the app |

---

## Discord upload behaviour

- Each blueprint is sent **immediately on detection** as a structured embed via the configured webhook
- The embed contains your Discord User ID and Guild Token so the bot can attribute and validate the entry
- The bot processes the embed and deletes the message from the channel
- A local copy is always written to `blueprints.json` first — embeds can be resent any time via **Sync to Discord**
- **Uploads are blocked** if Webhook URL, Guild Token, or Discord User ID are not configured — a single actionable error dialog is shown
- On upload failure a dialog is shown with the error; local data is never lost

---

## Link handshake — how it works

The app and bot communicate entirely through Discord's webhook REST API — no separate server required:

1. App POSTs a link-request embed (footer = link token) to the webhook with `?wait=true`, receiving the `message_id`
2. Bot sees the message via the Discord gateway, matches the token to the user who ran `/blueprint-link`, and edits the message title to `"Application Link SUCCESS"` with the User ID in a field
3. App polls `GET /webhooks/{id}/{token}/messages/{message_id}` every 2 seconds until the title matches, reads the User ID, then deletes the message
4. User ID is saved to `config.ini` — no further linking needed unless resetting

---

## Disclaimer

This application and the Star Citizen Blueprint Bot and its outputs are not endorsed by Cloud Imperium or Roberts Space Industries group of companies. All game content and materials are copyright Cloud Imperium Rights LLC and Cloud Imperium Rights Ltd.. Star Citizen®, Squadron 42®, Roberts Space Industries®, and Cloud Imperium® are registered trademarks of Cloud Imperium Rights LLC. All rights reserved.
