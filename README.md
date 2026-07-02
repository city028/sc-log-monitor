# SC Log Monitor

A lightweight Windows system-tray app that watches the Star Citizen `Game.log` in real time, detects blueprint drops, and sends them to a Discord channel via a Webhook-to-Bot Bridge.

---

## Features

- Detects blueprint drop notifications from `Game.log` in real time
- Appends each blueprint to a single persistent `blueprints.json` file (local backup)
- Backs up `blueprints.json` before every write (configurable max backups)
- Sends each blueprint immediately as a structured Discord embed via webhook
- Per-user identity via a one-time `/linkapp` token handshake (no shared webhook attribution)
- System tray icon with live session count and right-click menu
- All settings configurable via an in-app Settings dialog — no manual file editing

---

## Requirements

- Python 3.11+
- Install dependencies: `pip install -r requirements.txt`

```
pystray==0.19.5
Pillow==12.2.0
requests>=2.31.0
```

---

## Installation

1. Clone or download the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `config.ini.example` to `config.ini`
4. Launch via `launch.vbs` (runs silently, no console window) or `python sc_log_monitor.py`
5. On first run, output and backup directories default to:
   - Output: `Documents\Blueprints\blueprints.json`
   - Backups: `Documents\Blueprints\bak\`
6. Right-click the tray icon → **Settings** to configure paths and Discord

---

## Configuration

All settings are stored in `config.ini` and editable via the Settings dialog:

### General tab

| Setting | Description | Default |
|---------|-------------|---------|
| Game log file | Path to Star Citizen `Game.log` | `C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log` |
| Output directory | Where `blueprints.json` is written | `Documents\Blueprints` |
| Backup directory | Where timestamped backups are stored | `Documents\Blueprints\bak` |
| Max backups | How many backup files to keep | `10` |
| Poll interval | How often to check the log (seconds) | `1.0` |

### Discord tab

| Setting | Description |
|---------|-------------|
| Webhook URL | Channel webhook URL (provided by your server admin) |
| Bot API URL | Base URL of the bot's link-status endpoint (provided by your server admin) |
| Link Token | One-time token from `/linkapp` in Discord — enter and click **Link Account** to pair |
| Discord User ID | Populated automatically after successful link |
| Guild Token | Populated automatically after successful link — identifies you to the bot |

> **Security note:** Webhook URLs and bot API URLs should be provided by your server administrator during setup. Do not share them publicly.

---

## First-time Discord setup

1. In your Discord server run `/linkapp` — the bot responds with a one-time token
2. Open tray → **Settings** → **Discord** tab
3. Fill in **Webhook URL** and **Bot API URL** (provided by your admin)
4. Paste the token into **Link Token** and click **Link Account**
5. Wait up to 60 seconds — **Discord User ID** and **Guild Token** will populate when the bot confirms
6. Click **Save** — the app is now paired and will send embeds under your Discord identity

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
| Refresh stats | Updates the tooltip with the current session count and link status |
| Upload to Discord now | Resends all local blueprints.json entries as individual Discord embeds |
| Settings | Opens the settings dialog (General + Discord tabs) |
| Open output folder | Opens the output directory in Explorer |
| Quit | Exits the app |

---

## Discord upload behaviour

- Each blueprint is sent **immediately on detection** as a structured embed via the configured webhook
- The embed contains your Discord User ID and Guild Token so the bot can attribute and validate the entry
- The bot processes the embed and deletes the message from the channel
- A local copy is always written to `blueprints.json` first — embeds can be resent any time via **Upload to Discord now**
- On upload failure a dialog is shown with the error; local data is never lost
