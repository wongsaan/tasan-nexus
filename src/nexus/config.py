import json
from pathlib import Path

CONFIG_FILE = Path("config.json")

_DEFAULTS = {
    "data_dir": "~/Work/Backup/StardewValley/mods",
    "cookies_file": "nexus_cookies.json",
    "game_id": 1303,
    "game_domain": "stardewvalley",
    "game_dir": "~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods",
    "skip_extract": ["SMAPI - Stardew Modding API"],
}


def load() -> dict:
    if not CONFIG_FILE.exists():
        return dict(_DEFAULTS)
    data = json.loads(CONFIG_FILE.read_text())
    return {**_DEFAULTS, **data}


_cache: dict | None = None


def _cached() -> dict:
    global _cache
    if _cache is None:
        _cache = load()
    return _cache


def get(key: str):
    return _cached()[key]
