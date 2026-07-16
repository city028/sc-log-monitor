"""
SC Log Monitor — real-time Star Citizen log watcher.
Detects blueprint drops, appends them to a persistent local blueprints.json,
and sends a structured Discord embed via webhook for bot processing.
"""

import os
import re
import time
import shutil
import threading
import configparser
from datetime import datetime, timezone
from pathlib import Path

import json
import requests
import pystray
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_FILE = Path(__file__).parent / "config.ini"


def _get_documents_dir() -> Path:
    """Return the user's configured Documents folder (handles OneDrive redirection)."""
    try:
        import ctypes, ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
        return Path(buf.value)
    except Exception:
        return Path.home() / "Documents"


def _default_output_dir() -> Path:
    return _get_documents_dir() / "Blueprints"


def _default_bak_dir() -> Path:
    return _get_documents_dir() / "Blueprints" / "bak"


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding="utf-8")
    return config


def save_config(log_file: str, output_dir: str, bak_dir: str,
                max_backups: str, poll_interval: str,
                webhook_url: str, user_id: str, guild_token: str) -> None:
    """Write all settings back to config.ini."""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding="utf-8")

    if not config.has_section("paths"):
        config.add_section("paths")
    config.set("paths", "log_file",    log_file)
    config.set("paths", "output_dir",  output_dir)
    config.set("paths", "bak_dir",     bak_dir)
    config.set("paths", "max_backups", max_backups)

    if not config.has_section("monitor"):
        config.add_section("monitor")
    config.set("monitor", "poll_interval", poll_interval)

    if not config.has_section("discord"):
        config.add_section("discord")
    config.set("discord", "webhook_url", webhook_url)
    config.set("discord", "user_id",     user_id)
    config.set("discord", "guild_token", guild_token)

    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        config.write(fh)


# ---------------------------------------------------------------------------
# Event patterns
# ---------------------------------------------------------------------------

PATTERNS = [
    {
        "name": "blueprint",
        "regex": re.compile(r'Added notification "Received Blueprint: (.+?):\s*"'),
        "build": lambda m: {"item": m.group(1).strip()},
    },
]


# ---------------------------------------------------------------------------
# Persistent local JSON store
# ---------------------------------------------------------------------------

_file_lock = threading.Lock()


def _blueprints_path(output_dir: Path) -> Path:
    return output_dir / "blueprints.json"


def append_blueprint(output_dir: Path, bak_dir: Path, item: str,
                     max_backups: int = 10) -> tuple[str, bool]:
    """Backup blueprints.json, add or update the entry, return (timestamp, is_new).

    is_new=True  — item was not present, a new entry was appended.
    is_new=False — item already existed, only the timestamp was updated.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _blueprints_path(output_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with _file_lock:
        if path.exists():
            bak_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(path, bak_dir / f"blueprints_{stamp}.json")
            existing = sorted(bak_dir.glob("blueprints_*.json"))
            for old in existing[:-max_backups]:
                old.unlink(missing_ok=True)
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = []

        match = next((e for e in data if e["item"] == item), None)
        if match:
            match["timestamp"] = timestamp
            is_new = False
        else:
            data.append({"item": item, "timestamp": timestamp})
            is_new = True

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    return timestamp, is_new


def _load_total_blueprints(output_dir: Path) -> int:
    path = _blueprints_path(output_dir)
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return len(json.load(fh))
    except Exception:
        return 0


def _load_all_blueprints(output_dir: Path) -> list:
    path = _blueprints_path(output_dir)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def _show_message(title: str, message: str) -> None:
    """Show a message dialog in a background thread."""
    def _run():
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    threading.Thread(target=_run, daemon=True, name="notify-dialog").start()


# ---------------------------------------------------------------------------
# Discord embed upload
# ---------------------------------------------------------------------------

def _check_discord_ready(webhook_url: str, user_id: str, guild_token: str,
                         on_failure) -> bool:
    """Return True if all Discord credentials are present, else call on_failure and return False."""
    if not webhook_url:
        on_failure("Discord webhook URL is not configured.\nGo to Settings → Discord to add it.")
        return False
    if not guild_token:
        on_failure("Guild Token is not configured.\nGo to Settings → Discord to add it.")
        return False
    if not user_id:
        on_failure(
            "Discord account is not linked yet.\n"
            "Run /blueprint-link in Discord, then go to Settings → Discord → Link Account."
        )
        return False
    return True


def post_blueprint_embed(webhook_url: str, user_id: str, guild_token: str,
                         item: str, timestamp: str, on_failure) -> None:
    """POST a single blueprint as a Discord embed via webhook.

    Runs in the calling thread — callers should spawn a daemon thread.
    """
    if not _check_discord_ready(webhook_url, user_id, guild_token, on_failure):
        return
    try:
        payload = {
            "embeds": [{
                "title":  "\U0001f535 Star Citizen Blueprint Sync",
                "color":  242424,
                "fields": [
                    {"name": "User_ID",        "value": user_id, "inline": True},
                    {"name": "Blueprint_Name", "value": item,    "inline": True},
                ],
                "footer":    {"text": guild_token},
                "timestamp": timestamp,
            }]
        }
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if not resp.ok:
            on_failure(f"Discord upload failed: HTTP {resp.status_code}")
    except Exception as exc:
        on_failure(f"Discord upload error: {exc}")


def resend_all_from_local(webhook_url: str, user_id: str, guild_token: str,
                          output_dir: Path, on_failure) -> None:
    """Re-send every entry in blueprints.json as individual embeds."""
    if not _check_discord_ready(webhook_url, user_id, guild_token, on_failure):
        return
    entries = _load_all_blueprints(output_dir)
    if not entries:
        _show_message("SC Log Monitor", "No local blueprints found — nothing to resend.")
        return
    for entry in entries:
        post_blueprint_embed(webhook_url, user_id, guild_token,
                             entry["item"], entry["timestamp"], on_failure)
        time.sleep(0.5)   # avoid hitting Discord rate limits


# ---------------------------------------------------------------------------
# Link account handshake
# ---------------------------------------------------------------------------

def _parse_webhook_parts(webhook_url: str) -> tuple[str, str]:
    """Extract (webhook_id, webhook_token) from a Discord webhook URL."""
    # URL form: https://discord.com/api/webhooks/{id}/{token}
    parts = webhook_url.rstrip("/").split("/")
    if len(parts) < 2:
        raise ValueError("Invalid webhook URL")
    return parts[-2], parts[-1]


def link_account(webhook_url: str, link_token: str, on_success, on_failure) -> None:
    """One-time pairing flow using the webhook message as a shared mailbox.

    Flow:
      1. POST a link-request embed to the webhook with ?wait=true → get message_id.
      2. Bot sees the message via gateway, resolves link_token → user_id, edits the
         message title to "Application Link SUCCESS" and writes user_id into a field.
      3. App polls GET /webhooks/{id}/{token}/messages/{message_id} every 2 s until
         the title matches, then reads user_id and deletes the message.

    on_success(user_id) — called with the resolved Discord user ID.
    on_failure(message) — called on timeout or HTTP error.
    Runs in the calling thread — spawn a daemon thread before calling.
    """
    if not webhook_url or not link_token:
        on_failure("Webhook URL and Link Token are both required.")
        return

    try:
        wh_id, wh_token = _parse_webhook_parts(webhook_url)
    except ValueError:
        on_failure("Webhook URL is not valid.")
        return

    base = f"https://discord.com/api/webhooks/{wh_id}/{wh_token}"

    # 1. POST the link-request embed; ?wait=true returns the created message JSON
    try:
        payload = {
            "embeds": [{
                "title": "Application Link Request",
                "footer": {"text": link_token.strip()},
            }]
        }
        resp = requests.post(f"{base}?wait=true", json=payload, timeout=15)
        if not resp.ok:
            on_failure(f"Link request failed: HTTP {resp.status_code}")
            return
        message_id = resp.json()["id"]
    except Exception as exc:
        on_failure(f"Link request error: {exc}")
        return

    # 2. Poll the message until the bot edits the title to the success sentinel
    msg_url  = f"{base}/messages/{message_id}"
    deadline = time.monotonic() + 60
    user_id  = None
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            r = requests.get(msg_url, timeout=10)
            if not r.ok:
                on_failure(f"Poll error: HTTP {r.status_code}")
                _try_delete_message(msg_url)
                return
            data   = r.json()
            embeds = data.get("embeds", [])
            if embeds and embeds[0].get("title") == "Application Link SUCCESS":
                # Bot writes user_id into a field named "User_ID" and also the footer
                fields    = embeds[0].get("fields", [])
                uid_field = next((f for f in fields if f.get("name") == "User_ID"), None)
                user_id   = uid_field["value"] if uid_field else embeds[0].get("footer", {}).get("text")
                break
        except Exception:
            pass  # transient — keep polling

    # 3. Delete the handshake message regardless of outcome
    _try_delete_message(msg_url)

    if user_id:
        on_success(user_id)
    else:
        on_failure("Link timed out after 60 seconds. Try /blueprint-link again in Discord.")


def _try_delete_message(msg_url: str) -> None:
    try:
        requests.delete(msg_url, timeout=10)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Log tailer
# ---------------------------------------------------------------------------

class LogTailer:
    def __init__(self, log_path: Path, output_dir: Path, bak_dir: Path,
                 poll_interval: float, on_event,
                 webhook_url: str = "", user_id: str = "", guild_token: str = "",
                 on_failure=None, max_backups: int = 10):
        self.log_path      = log_path
        self.output_dir    = output_dir
        self.bak_dir       = bak_dir
        self.poll_interval = poll_interval
        self.on_event      = on_event
        self.webhook_url   = webhook_url
        self.user_id       = user_id
        self.guild_token   = guild_token
        self.on_failure    = on_failure or (lambda msg: None)
        self.max_backups   = max_backups

        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="log-tailer")
        self.blueprints_session = 0
        self._last_fired: dict[str, float] = {}

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        fh = None
        last_size = -1

        while not self._stop.is_set():
            try:
                if not self.log_path.exists():
                    if fh:
                        fh.close()
                        fh = None
                        last_size = -1
                    self._stop.wait(self.poll_interval)
                    continue

                current_size = self.log_path.stat().st_size

                if fh is None:
                    fh = open(self.log_path, "r", encoding="utf-8", errors="replace")
                    fh.seek(0, 2)
                    last_size = current_size
                elif current_size < last_size:
                    fh.close()
                    fh = open(self.log_path, "r", encoding="utf-8", errors="replace")
                    fh.seek(0, 2)
                    last_size = current_size

                line = fh.readline()
                if not line:
                    last_size = current_size
                    self._stop.wait(self.poll_interval)
                    continue

                self._process_line(line)

            except Exception:
                if fh:
                    fh.close()
                    fh = None
                    last_size = -1
                self._stop.wait(self.poll_interval)

        if fh:
            fh.close()

    def _process_line(self, line: str):
        for pattern in PATTERNS:
            m = pattern["regex"].search(line)
            if not m:
                continue

            event_type = pattern["name"]

            cooldown = pattern.get("cooldown", 0)
            if cooldown:
                now = time.monotonic()
                if now - self._last_fired.get(event_type, 0) < cooldown:
                    break
                self._last_fired[event_type] = now

            attrs = pattern["build"](m)
            timestamp, is_new = append_blueprint(self.output_dir, self.bak_dir,
                                                 attrs["item"], self.max_backups)
            if is_new:
                self.blueprints_session += 1

            threading.Thread(
                target=post_blueprint_embed,
                args=(self.webhook_url, self.user_id, self.guild_token,
                      attrs["item"], timestamp, self.on_failure),
                daemon=True,
                name="discord-embed",
            ).start()

            self.on_event(event_type, attrs, is_new)
            break


# ---------------------------------------------------------------------------
# Settings dialog (tabbed tkinter)
# ---------------------------------------------------------------------------

def show_settings_dialog(on_saved):
    """Open a tabbed settings form in a background thread."""
    def _dialog():
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox

        config      = load_config()
        log_file    = config.get("paths",   "log_file",      fallback="")
        output_dir  = config.get("paths",   "output_dir",    fallback="")
        bak_dir     = config.get("paths",   "bak_dir",       fallback="")
        max_backups = config.get("paths",   "max_backups",   fallback="10")
        poll        = config.get("monitor", "poll_interval", fallback="1.0")
        webhook     = config.get("discord", "webhook_url",   fallback="")
        user_id     = config.get("discord", "user_id",       fallback="")
        guild_token = config.get("discord", "guild_token",   fallback="")

        root = tk.Tk()
        root.title("SC Log Monitor — Settings")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        nb  = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        tab_gen  = ttk.Frame(nb)
        tab_disc = ttk.Frame(nb)
        nb.add(tab_gen,  text="General")
        nb.add(tab_disc, text="Discord")

        pad = {"padx": 8, "pady": 4}

        # ── General tab ───────────────────────────────────────────────────
        tk.Label(tab_gen, text="Game log file:", anchor="w").grid(
            row=0, column=0, sticky="w", **pad)
        log_var = tk.StringVar(value=log_file)
        tk.Entry(tab_gen, textvariable=log_var, width=50).grid(row=0, column=1, **pad)
        def browse_log():
            p = filedialog.askopenfilename(
                title="Select Game.log",
                filetypes=[("Log files", "*.log"), ("All files", "*.*")])
            if p: log_var.set(p)
        tk.Button(tab_gen, text="Browse…", command=browse_log).grid(row=0, column=2, **pad)

        tk.Label(tab_gen, text="Output directory:", anchor="w").grid(
            row=1, column=0, sticky="w", **pad)
        dir_var = tk.StringVar(value=output_dir)
        tk.Entry(tab_gen, textvariable=dir_var, width=50).grid(row=1, column=1, **pad)
        def browse_dir():
            p = filedialog.askdirectory(title="Select output directory")
            if p: dir_var.set(p)
        tk.Button(tab_gen, text="Browse…", command=browse_dir).grid(row=1, column=2, **pad)

        tk.Label(tab_gen, text="Backup directory:", anchor="w").grid(
            row=2, column=0, sticky="w", **pad)
        bak_var = tk.StringVar(value=bak_dir)
        tk.Entry(tab_gen, textvariable=bak_var, width=50).grid(row=2, column=1, **pad)
        def browse_bak():
            p = filedialog.askdirectory(title="Select backup directory")
            if p: bak_var.set(p)
        tk.Button(tab_gen, text="Browse…", command=browse_bak).grid(row=2, column=2, **pad)

        tk.Label(tab_gen, text="Max backups to keep:", anchor="w").grid(
            row=3, column=0, sticky="w", **pad)
        bak_count_var = tk.StringVar(value=max_backups)
        tk.Entry(tab_gen, textvariable=bak_count_var, width=10).grid(
            row=3, column=1, sticky="w", **pad)

        tk.Label(tab_gen, text="Poll interval (seconds):", anchor="w").grid(
            row=4, column=0, sticky="w", **pad)
        poll_var = tk.StringVar(value=poll)
        tk.Entry(tab_gen, textvariable=poll_var, width=10).grid(
            row=4, column=1, sticky="w", **pad)

        # ── Discord tab ───────────────────────────────────────────────────
        tk.Label(tab_disc, text="Webhook URL:", anchor="w").grid(
            row=0, column=0, sticky="w", **pad)
        hook_var = tk.StringVar(value=webhook)
        tk.Entry(tab_disc, textvariable=hook_var, width=55).grid(
            row=0, column=1, columnspan=2, sticky="we", **pad)

        tk.Label(tab_disc, text="Guild Token:", anchor="w").grid(
            row=1, column=0, sticky="w", **pad)
        gt_var = tk.StringVar(value=guild_token)
        tk.Entry(tab_disc, textvariable=gt_var, width=55).grid(
            row=1, column=1, columnspan=2, sticky="we", **pad)

        ttk.Separator(tab_disc, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="we", pady=6)
        tk.Label(tab_disc, text="Link Account", font=("", 9, "bold")).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=8)
        tk.Label(tab_disc,
                 text="Run /blueprint-link in Discord, paste the token below, then click Link Account.",
                 anchor="w", foreground="grey").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=8)

        tk.Label(tab_disc, text="Link Token:", anchor="w").grid(
            row=5, column=0, sticky="w", **pad)
        token_var = tk.StringVar()
        tk.Entry(tab_disc, textvariable=token_var, width=20).grid(
            row=5, column=1, sticky="w", **pad)

        link_status = tk.StringVar(value="")
        tk.Label(tab_disc, textvariable=link_status, foreground="grey").grid(
            row=5, column=2, sticky="w", **pad)

        ttk.Separator(tab_disc, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="we", pady=6)

        tk.Label(tab_disc, text="Discord User ID:", anchor="w").grid(
            row=7, column=0, sticky="w", **pad)
        uid_var = tk.StringVar(value=user_id)
        tk.Entry(tab_disc, textvariable=uid_var, width=30, state="readonly").grid(
            row=7, column=1, sticky="w", **pad)

        def do_link():
            link_status.set("Linking…")
            def on_success(uid):
                uid_var.set(uid)
                token_var.set("")
                link_status.set("Linked!")
                save_config(
                    log_var.get().strip(), dir_var.get().strip(),
                    bak_var.get().strip(), bak_count_var.get().strip(),
                    poll_var.get().strip(), hook_var.get().strip(),
                    uid, gt_var.get().strip(),
                )
            def on_fail(msg):
                link_status.set("Failed")
                _show_message("Link Failed", msg)
            threading.Thread(
                target=link_account,
                args=(hook_var.get().strip(), token_var.get().strip(),
                      on_success, on_fail),
                daemon=True, name="link-account",
            ).start()

        tk.Button(tab_disc, text="Link Account", command=do_link).grid(
            row=8, column=1, sticky="w", **pad)

        ttk.Separator(tab_disc, orient="horizontal").grid(
            row=9, column=0, columnspan=3, sticky="we", pady=6)

        def do_reset():
            hook_var.set("")
            gt_var.set("")
            uid_var.set("")
            token_var.set("")
            link_status.set("")

        tk.Button(tab_disc, text="Reset Discord Settings", command=do_reset,
                  foreground="red").grid(row=10, column=1, sticky="w", **pad)

        # ── Save / Cancel ─────────────────────────────────────────────────
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=8)

        def on_save():
            try:
                float(poll_var.get())
            except ValueError:
                messagebox.showerror("Invalid value", "Poll interval must be a number.")
                return
            try:
                int(bak_count_var.get())
            except ValueError:
                messagebox.showerror("Invalid value", "Max backups must be a whole number.")
                return
            save_config(
                log_var.get().strip(), dir_var.get().strip(),
                bak_var.get().strip(), bak_count_var.get().strip(),
                poll_var.get().strip(), hook_var.get().strip(),
                uid_var.get().strip(), gt_var.get().strip(),
            )
            root.destroy()
            on_saved()

        tk.Button(btn_frame, text="Save",   width=10, command=on_save).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Cancel", width=10, command=root.destroy).pack(side="left", padx=4)

        root.mainloop()

    threading.Thread(target=_dialog, daemon=True, name="settings-dialog").start()


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------

_ICON_PATH = Path(__file__).parent / "src" / "bot-avatar.png"


def _make_icon() -> Image.Image:
    try:
        return Image.open(_ICON_PATH).convert("RGBA").resize((64, 64), Image.LANCZOS)
    except Exception:
        size = 64
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, size - 2, size - 2], fill="#1a6b3c")
        try:
            font = ImageFont.truetype("arialbd.ttf", 22)
        except Exception:
            font = ImageFont.load_default()
        draw.text((size // 2, size // 2), "SC", font=font, fill="white", anchor="mm")
        return img


def run_tray(tailer_ref: list, output_dir_ref: list, on_event_fn):
    def tooltip() -> str:
        t = tailer_ref[0]
        status = "linked" if t.user_id else "not linked"
        total  = _load_total_blueprints(output_dir_ref[0])
        return (
            f"SC Log Monitor\n"
            f"--------------------\n"
            f"Status: {status}\n"
            f"Session Blueprints: {t.blueprints_session}\n"
            f"Total Blueprints: {total}"
        )

    def on_open_folder(icon, item):
        os.startfile(str(output_dir_ref[0]))

    def on_stats(icon, item):
        icon.title = tooltip()

    def on_quit(icon, item):
        tailer_ref[0].stop()
        icon.stop()

    def on_upload_failure(message: str):
        _show_message("SC Log Monitor — Upload Failed", message)

    tailer_ref[0].on_failure = on_upload_failure

    def on_upload_now(icon, item):
        t = tailer_ref[0]
        threading.Thread(
            target=resend_all_from_local,
            args=(t.webhook_url, t.user_id, t.guild_token,
                  t.output_dir, on_upload_failure),
            daemon=True,
            name="discord-resend",
        ).start()

    def on_settings(icon, item):
        def restart_tailer():
            tailer_ref[0].stop()
            config      = load_config()
            log_path    = Path(config.get("paths",   "log_file"))
            output_dir  = Path(config.get("paths",   "output_dir",
                                           fallback=str(_default_output_dir())))
            bak_dir     = Path(config.get("paths",   "bak_dir",
                                           fallback=str(_default_bak_dir())))
            max_backups = config.getint("paths",    "max_backups",   fallback=10)
            poll_sec    = config.getfloat("monitor", "poll_interval", fallback=1.0)
            webhook     = config.get("discord", "webhook_url",  fallback="")
            user_id     = config.get("discord", "user_id",      fallback="")
            guild_token = config.get("discord", "guild_token",  fallback="")
            output_dir_ref[0] = output_dir
            new_tailer = LogTailer(log_path, output_dir, bak_dir, poll_sec,
                                   on_event_fn, webhook, user_id, guild_token,
                                   on_upload_failure, max_backups)
            tailer_ref[0] = new_tailer
            new_tailer.start()
            icon.title = tooltip()

        show_settings_dialog(on_saved=restart_tailer)

    icon = pystray.Icon(
        name="sc-log-monitor",
        icon=_make_icon(),
        title=tooltip(),
        menu=pystray.Menu(
            pystray.MenuItem("Refresh stats",         on_stats),
            pystray.MenuItem("Upload to Discord now", on_upload_now),
            pystray.MenuItem("Settings",              on_settings),
            pystray.MenuItem("Open output folder",    on_open_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        ),
    )

    def _refresh_loop():
        while not tailer_ref[0]._stop.is_set():
            icon.title = tooltip()
            time.sleep(30)

    threading.Thread(target=_refresh_loop, daemon=True, name="tooltip-refresh").start()
    icon.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    config      = load_config()
    log_path    = Path(config.get("paths",   "log_file"))
    output_dir  = Path(config.get("paths",   "output_dir",
                                   fallback=str(_default_output_dir())))
    bak_dir     = Path(config.get("paths",   "bak_dir",
                                   fallback=str(_default_bak_dir())))
    max_backups = config.getint("paths",    "max_backups",   fallback=10)
    poll_sec    = config.getfloat("monitor", "poll_interval", fallback=1.0)
    webhook     = config.get("discord", "webhook_url",  fallback="")
    user_id     = config.get("discord", "user_id",      fallback="")
    guild_token = config.get("discord", "guild_token",  fallback="")

    if not config.has_option("paths", "output_dir") or not config.has_option("paths", "bak_dir"):
        save_config(str(log_path), str(output_dir), str(bak_dir),
                    str(max_backups), str(poll_sec),
                    webhook, user_id, guild_token)

    def on_event(event_type: str, attrs: dict, is_new: bool = True):
        ts = datetime.now().strftime("%H:%M:%S")
        if event_type == "blueprint":
            if is_new:
                print(f"[{ts}] Blueprint received: {attrs['item']}")
            else:
                print(f"[{ts}] Blueprint already owned, timestamp updated: {attrs['item']}")
        else:
            print(f"[{ts}] {event_type}: {attrs}")

    tailer = LogTailer(log_path, output_dir, bak_dir, poll_sec,
                       on_event, webhook, user_id, guild_token,
                       max_backups=max_backups)
    tailer.start()

    print("SC Log Monitor started.")
    print(f"  Watching : {log_path}")
    print(f"  Output   : {output_dir}")
    print(f"  Backups  : {bak_dir}")
    linked = f"User {user_id}" if user_id else "not linked"
    print(f"  Discord  : {linked}")
    print(f"  Tray icon active — right-click it to open folder or quit.")

    run_tray([tailer], [output_dir], on_event)


if __name__ == "__main__":
    main()
