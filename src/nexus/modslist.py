"""管理 mods_list.json —— 已安装合集的注册表。"""

import json
from datetime import datetime, timezone
from pathlib import Path

MODS_LIST_FILE = Path("mods_list.json")


def load() -> dict:
    if not MODS_LIST_FILE.exists():
        return {}
    return json.loads(MODS_LIST_FILE.read_text())


def save(data: dict):
    MODS_LIST_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def add(url: str, name: str, installed: bool = False):
    data = load()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if url in data:
        data[url]["updated_at"] = now
        if installed:
            data[url]["installed"] = True
    else:
        data[url] = {
            "name": name,
            "installed_at": now,
            "updated_at": now,
            "installed": installed,
        }
    save(data)
