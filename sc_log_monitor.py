"""
SC Log Monitor — real-time Star Citizen log watcher.
Detects in-game events (aUEC payouts, blueprint drops, …) and writes
them to per-day XML files in the configured output directory.
"""

import os
import re
import sys
import time
import threading
import configparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_FILE = Path(__file__).parent / "config.ini"

def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding="utf-8")
    return config


# ---------------------------------------------------------------------------
# Event patterns
#
# To add a new event type, append a dict to PATTERNS with:
#   name     – human-readable label
#   regex    – compiled pattern; must match lines that carry the event
#   build    – callable(re.Match) → dict of XML attributes (without "type")
#   cooldown – (optional) seconds to suppress duplicate matches; useful when
#              a single in-game event produces many matching log lines
# ---------------------------------------------------------------------------

def _strip_id_suffix(name: str) -> str:
    """Remove trailing numeric ID from entity/vehicle names (e.g. DRAK_Golem_OX_629940747186)."""
    return re.sub(r'_\d+$', '', name.strip())


PATTERNS = [
    {
        "name": "aUEC",
        "regex": re.compile(r'Added notification "Awarded (\d+) aUEC'),
        "build": lambda m: {"amount": m.group(1)},
    },
    {
        "name": "blueprint",
        "regex": re.compile(r'Added notification "Received Blueprint: (.+?):\s*"'),
        "build": lambda m: {"item": m.group(1).strip()},
    },
    {
        # Vehicle destroyed while you were pilot — collision with terrain/entity
        "name": "death_vehicle",
        "regex": re.compile(
            r'<FatalCollision> Fatal Collision occured for vehicle (\S+)'
            r'.*?Zone: (\w+), PlayerPilot: 1\]'
            r' after hitting entity: ([^\[]+)'
        ),
        "build": lambda m: {
            "ship":       _strip_id_suffix(m.group(1)),
            "zone":       m.group(2),
            "hit_entity": _strip_id_suffix(m.group(3)),
        },
    },
    {
        # On-foot death (player killed, suffocation, etc.)
        # This log line fires once per equipped item — cooldown collapses them
        # into a single event.
        "name": "death_onfoot",
        "regex": re.compile(r'CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement'),
        "build": lambda m: {},
        "cooldown": 10,   # seconds
    },
]


# ---------------------------------------------------------------------------
# XML persistence — one file per calendar day, events appended in real time
# ---------------------------------------------------------------------------

_xml_lock = threading.Lock()


def _daily_path(output_dir: Path) -> Path:
    return output_dir / f"{datetime.now().strftime('%Y-%m-%d')}.xml"


def append_event(output_dir: Path, event_type: str, attrs: dict) -> None:
    """Append one event element to today's XML file, creating it if needed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _daily_path(output_dir)

    with _xml_lock:
        if path.exists():
            tree = ET.parse(path)
            root = tree.getroot()
        else:
            root = ET.Element("log", date=datetime.now().strftime("%Y-%m-%d"))
            tree = ET.ElementTree(root)

        all_attrs = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        all_attrs.update(attrs)
        ET.SubElement(root, "event", **all_attrs)

        ET.indent(root, space="  ")
        tree.write(path, encoding="unicode", xml_declaration=True)


def _load_daily_totals(output_dir: Path) -> tuple[int, int, int, int]:
    """Read today's XML and return (auec, blueprints, deaths, events)."""
    path = _daily_path(output_dir)
    if not path.exists():
        return 0, 0, 0, 0
    try:
        root = ET.parse(path).getroot()
        auec = blueprints = deaths = events = 0
        for ev in root.findall("event"):
            t = ev.get("type", "")
            events += 1
            if t == "aUEC":
                auec += int(ev.get("amount", 0))
            elif t == "blueprint":
                blueprints += 1
            elif t in ("death_vehicle", "death_onfoot"):
                deaths += 1
        return auec, blueprints, deaths, events
    except Exception:
        return 0, 0, 0, 0


# ---------------------------------------------------------------------------
# Log tailer — follows Game.log, restarts automatically on file replacement
# (Star Citizen creates a fresh Game.log each session)
# ---------------------------------------------------------------------------

class LogTailer:
    def __init__(self, log_path: Path, output_dir: Path,
                 poll_interval: float, on_event):
        self.log_path = log_path
        self.output_dir = output_dir
        self.poll_interval = poll_interval
        self.on_event = on_event          # callback(event_type, attrs)

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="log-tailer")
        # running totals for today — pre-populated from today's XML if it exists
        self._today = datetime.now().date()
        self.auec_today, self.blueprints_today, self.deaths_today, self.events_today = \
            _load_daily_totals(output_dir)
        # last-fired timestamps for cooldown-based deduplication
        self._last_fired: dict[str, float] = {}

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _reset_daily_totals_if_needed(self):
        today = datetime.now().date()
        if today != self._today:
            self._today = today
            self.auec_today = 0
            self.blueprints_today = 0
            self.deaths_today = 0
            self.events_today = 0

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
                    # First open — seek to end so we only catch live events
                    fh = open(self.log_path, "r", encoding="utf-8",
                               errors="replace")
                    fh.seek(0, 2)
                    last_size = current_size
                elif current_size < last_size:
                    # File was replaced (new game session) — reopen from end
                    fh.close()
                    fh = open(self.log_path, "r", encoding="utf-8",
                               errors="replace")
                    fh.seek(0, 2)
                    last_size = current_size

                line = fh.readline()
                if not line:
                    last_size = current_size
                    self._stop.wait(self.poll_interval)
                    continue

                self._reset_daily_totals_if_needed()
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

            # Cooldown check — suppress duplicate firings within N seconds
            cooldown = pattern.get("cooldown", 0)
            if cooldown:
                now = time.monotonic()
                if now - self._last_fired.get(event_type, 0) < cooldown:
                    break
                self._last_fired[event_type] = now

            attrs = pattern["build"](m)
            append_event(self.output_dir, event_type, attrs)

            self.events_today += 1
            if event_type == "aUEC":
                self.auec_today += int(attrs["amount"])
            elif event_type == "blueprint":
                self.blueprints_today += 1
            elif event_type in ("death_vehicle", "death_onfoot"):
                self.deaths_today += 1

            self.on_event(event_type, attrs)
            break   # one pattern per line is enough


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------

def _make_icon() -> Image.Image:
    """Draw a simple 64×64 icon: dark-green circle with 'SC' text."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill="#1a6b3c")
    # Use default bitmap font (always available, no file needed)
    try:
        font = ImageFont.truetype("arialbd.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.text((size // 2, size // 2), "SC", font=font, fill="white",
              anchor="mm")
    return img


def run_tray(tailer: LogTailer, output_dir: Path):
    def tooltip() -> str:
        return (
            f"SC Log Monitor\n"
            f"Today: {tailer.auec_today:,} aUEC  |  "
            f"{tailer.blueprints_today} blueprint(s)  |  "
            f"{tailer.deaths_today} death(s)  |  "
            f"{tailer.events_today} event(s)"
        )

    def on_open_folder(icon, item):
        os.startfile(str(output_dir))

    def on_stats(icon, item):
        icon.title = tooltip()

    def on_quit(icon, item):
        tailer.stop()
        icon.stop()

    icon = pystray.Icon(
        name="sc-log-monitor",
        icon=_make_icon(),
        title=tooltip(),
        menu=pystray.Menu(
            pystray.MenuItem("Refresh stats", on_stats),
            pystray.MenuItem("Open output folder", on_open_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        ),
    )

    # Keep the tooltip fresh every 30 s without blocking the tray thread
    def _refresh_loop():
        while not tailer._stop.is_set():
            icon.title = tooltip()
            time.sleep(30)

    threading.Thread(target=_refresh_loop, daemon=True,
                     name="tooltip-refresh").start()

    icon.run()   # blocks until Quit is selected


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    config = load_config()

    log_path   = Path(config.get("paths", "log_file"))
    output_dir = Path(config.get("paths", "output_dir"))
    poll_sec   = config.getfloat("monitor", "poll_interval", fallback=1.0)

    def on_event(event_type: str, attrs: dict):
        # Console feedback when not running as a pure background process
        ts = datetime.now().strftime("%H:%M:%S")
        if event_type == "aUEC":
            print(f"[{ts}] aUEC awarded: {int(attrs['amount']):,}")
        elif event_type == "blueprint":
            print(f"[{ts}] Blueprint received: {attrs['item']}")
        elif event_type == "death_vehicle":
            print(f"[{ts}] Vehicle death: {attrs['ship']} hit {attrs['hit_entity']} in {attrs['zone']}")
        elif event_type == "death_onfoot":
            print(f"[{ts}] On-foot death")
        else:
            print(f"[{ts}] {event_type}: {attrs}")

    tailer = LogTailer(log_path, output_dir, poll_sec, on_event)
    tailer.start()

    print(f"SC Log Monitor started.")
    print(f"  Watching : {log_path}")
    print(f"  Output   : {output_dir}")
    print(f"  Tray icon active — right-click it to open folder or quit.")

    run_tray(tailer, output_dir)


if __name__ == "__main__":
    main()
