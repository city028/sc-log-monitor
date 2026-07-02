# SC Log Monitor

A lightweight Windows system-tray app that watches the Star Citizen `Game.log` in real time, detects blueprint drops, and uploads a persistent record to a Discord channel via webhook.

---

## Features

- Detects blueprint drop notifications from `Game.log`
- Appends each blueprint to a single persistent `blueprints.json` file
- Automatically backs up the JSON before every write (configurable max backups)
- Uploads the full JSON to Discord at end of session, or on demand from the tray menu
- System tray icon with live session stats and right-click menu
- All settings configurable via in-app Settings dialog (no manual config editing needed)

---

## Requirements

- Python 3.11+
- Dependencies: `pip install -r requirements.txt`

```
pystray==0.19.5
Pillow==12.2.0
requests>=2.31.0
```

---

## Installation

1. Clone or download the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Launch via `launch.vbs` (runs silently, no console window) or `python sc_log_monitor.py`
4. On first run, output and backup directories default to:
   - Output: `Documents\Blueprints\blueprints.json`
   - Backups: `Documents\Blueprints\bak\`
5. Right-click the tray icon → **Settings** to configure paths and Discord webhook

---

## Configuration

All settings are stored in `config.ini` and editable via the Settings dialog:

| Setting | Description | Default |
|---------|-------------|---------|
| Game log file | Path to Star Citizen `Game.log` | `C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log` |
| Output directory | Where `blueprints.json` is written | `Documents\Blueprints` |
| Backup directory | Where timestamped backups are stored | `Documents\Blueprints\bak` |
| Discord webhook URL | Webhook to post the JSON file to | _(empty)_ |
| Poll interval | How often to check the log (seconds) | `1.0` |
| Max backups | How many backup files to keep | `10` |

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

A flat list — one entry per blueprint, ordered by time of detection. The file grows across all sessions indefinitely.

---

## Tray menu

| Item | Action |
|------|--------|
| Refresh stats | Updates the tooltip with the current session count |
| Upload to Discord now | Manually triggers a Discord upload of the full JSON |
| Settings | Opens the settings dialog |
| Open output folder | Opens the output directory in Explorer |
| Quit | Uploads to Discord (if blueprints received this session) then exits |

---

## Known limitations

- aUEC payout amounts are not reliably logged by Star Citizen — the monitor does not track them
- The `death_onfoot` pattern can fire on ALT-F4 (client-side cleanup) rather than a true in-game death — this was observed and left in for further data gathering
- Discord webhook file uploads are limited to 8 MB (the JSON file is unlikely to approach this)

---

## Discord upload behaviour

- Upload triggers automatically at **end of session**: when SC restarts (log file replaced) or when the user clicks Quit
- Upload only fires if at least one blueprint was received in the current session
- A manual upload is always available via the tray menu regardless of session state
- On upload failure a dialog is shown with the error message
