# SC Log Monitor — Notes

## Architecture

Single-file Python app (`sc_log_monitor.py`) with four logical layers:

1. **Config** — `load_config()` / `save_config()` read/write `config.ini`. Defaults computed at runtime from the Windows Documents folder via `SHGetFolderPathW` (handles OneDrive redirection).

2. **Persistence** — `append_blueprint()` maintains a single `blueprints.json` flat list. Backs up the file before every write, pruning to `max_backups` most recent.

3. **LogTailer** — daemon thread that polls `Game.log`. Seeks to end on open (live events only). Detects file replacement (new SC session) by size decrease. Fires `_on_session_end()` on replacement or Quit.

4. **Tray UI** — `pystray` icon with tkinter-based Settings dialog and notifications (Windows 11 balloon tips are unreliable; tkinter `showinfo` used instead).

## Key files

| File | Purpose |
|------|---------|
| `sc_log_monitor.py` | All application logic |
| `config.ini` | Runtime configuration |
| `launch.vbs` | Silent launcher (no console window) |
| `src/bot-avatar.png` | Tray icon image |
| `{output_dir}/blueprints.json` | Persistent blueprint record |
| `{bak_dir}/blueprints_YYYYMMDD_HHMMSS.json` | Timestamped backups |

## Star Citizen log observations

- Blueprint pattern: `Added notification "Received Blueprint: <item>: "`
- aUEC pattern (`Added notification "Awarded \d+ aUEC"`) exists in code but is inconsistently logged by SC — not always present after missions
- `death_onfoot` fires on `CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement` — also triggers on ALT-F4, needs more data to distinguish
- `Contract Complete` notifications appear for mission completion but contain no aUEC amount

## Next steps (pre-distribution)

- Package with PyInstaller as standalone `.exe`
- Harden first-run: validate `log_file` path exists, show setup guidance if not
- Consider README / user-facing install docs
