# tasan-nexus

Nexus Mods collection downloader.

Download Nexus Mods collections via GraphQL API — no browser needed.

[中文版 · Chinese](README_zh.md)

---

## Features

- **Login**: Auto-read cookies from Chrome, Firefox, Safari, Edge
- **Install**: Backup → download → extract → config routing, all in one
- **Update**: Check latest versions, replace outdated files
- **Download**: Download zips only, no extraction
- **Interactive list**: `list` shows installed collections. Number = install, `u`+number = update, `q` = quit

### Details

- **Deferred config routing**: Wait until all mods are extracted before writing `config.json`, avoiding missing-directory errors
- **Multi-file mod pages**: Same `mod_id`, different files — e.g. East Scarp has Remastered and Compatibility Fixes, neither gets accidentally deleted
- **Update by file name**: Frontier Farm won't be replaced by Immersive Farm — each file matches its own latest version
- **Cross-collection dedup**: Same mod + same version across collections → reuse the existing download
- **Optional mods**: Optional files stored in `Optional/` subdirectory
- **Skip extract**: Skip extraction for mod loaders like SMAPI via `skip_extract` config

---

## Installation

```bash
git clone git@github.com:wongsaan/tasan-nexus.git
cd tasan-nexus
uv sync
```

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

---

## Login

Log in at [nexusmods.com](https://www.nexusmods.com/) in your browser, then:

```bash
uv run tasan-nexus login
```

Auto-reads cookies from your browser and saves them to `nexus_cookies.json`.

> Manual: F12 → Application → Cookies, copy **all** cookies from nexusmods.com and create `nexus_cookies.json`:
> ```json
> [
>   {"name": "nexusmods_session", "value": "..."},
>   {"name": "nexusmods_session_refresh", "value": "..."},
>   {"name": "__cf_bm", "value": "..."},
>   {"name": "cf_clearance", "value": "..."},
>   {"name": "__cflb", "value": "..."}
> ]
> ```

---

## Usage

```bash
# Login
uv run tasan-nexus login

# Install (backup → download → extract → config routing)
uv run tasan-nexus install https://www.nexusmods.com/games/stardewvalley/collections/tckf0m/mods

# Download only
uv run tasan-nexus download https://www.nexusmods.com/games/stardewvalley/collections/tckf0m/mods

# Update all collections
uv run tasan-nexus update

# Interactive list
uv run tasan-nexus list
```

`install` and `update` back up the Mods directory to `Mods.backup.YYYY-MM-DD/` before making changes.

---

## Command Comparison

| | download | install | update |
|---|---|---|---|
| Download zip | ✔ | ✔ | ✔ |
| Extract | — | ✔ | by `installed` flag |
| Backup | — | ✔ | by `installed` flag |
| Config routing | — | deferred | deferred |
| Version source | collection | collection | latest upload |
| Remove old | — | — | ✔ |

---

## Configuration

Place `config.json` in the project root to override defaults.

```json
{
  "data_dir": "~/Work/Backup/StardewValley/mods",
  "cookies_file": "nexus_cookies.json",
  "game_id": 1303,
  "game_domain": "stardewvalley",
  "game_dir": "~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods",
  "skip_extract": ["SMAPI - Stardew Modding API"]
}
```

| Field | Description |
|---|---|
| `data_dir` | zip cache directory |
| `cookies_file` | cookies file path |
| `game_id` | numeric game ID (Stardew Valley = 1303) |
| `game_domain` | game domain slug |
| `game_dir` | game Mods directory, extraction target |
| `skip_extract` | mod names to skip extraction |

---

## Key Files

| File | Description |
|---|---|
| `nexus_cookies.json` | login session |
| `mods_list.json` | collection registry `{url: {name, installed_at, updated_at, installed}}` |
| `.downloaded.json` | per-collection manifest `{file_id: {name, version, optional, mod_id, file_title}}` |
| `config.json` | user config (optional) |

### `.downloaded.json` Format

```json
{
  "135999": {
    "name": "Frontier Farm-3753-1-15-11-1751325482.zip",
    "version": "1.15.11",
    "optional": false,
    "mod_id": "3753",
    "file_title": "Frontier Farm"
  }
}
```

- key = `file_id`: unique upload ID on Nexus
- `mod_id`: mod page ID
- `file_title`: file title on the mod page, used to distinguish files sharing the same `mod_id`

---

## Config Presets

Zips containing only `config.json` — no dlls or resource files. Instead of extracting the whole archive, each `config.json` is copied to `game_dir` using the exact path from inside the zip. Skipped if the target directory doesn't exist.

---

## Archive Support

| Format | Implementation |
|---|---|
| `.zip` | `zipfile` (Python built-in) |
| `.7z` | `py7zr` (pure Python) |
| `.rar` | `bsdtar` / `unrar` / `7z` (auto-detect) |

---

## Architecture

```
src/nexus/
├── main.py          # CLI entry point
├── collection.py    # GraphQL API client
├── downloader.py    # download & manifest management
├── extractor.py     # backup, extract, config routing
├── config.py        # config loader
└── modslist.py      # collection registry CRUD
```
