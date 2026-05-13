import json
import shutil
import time
from pathlib import Path
from urllib.parse import unquote
import httpx

from nexus.config import get as config_get
from nexus.extractor import _is_config_preset, extract_mod, _list_archive

MANIFEST_FILE = ".downloaded.json"


def sync_manifest(mods: list[dict], collection_dir: Path):
    """Sync manifest with API data: upgrade old format, backfill versions, migrate optional mods."""
    manifest_path = collection_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict):
        return
    updated = 0
    migrated = 0
    optional_dir = collection_dir / "Optional"

    for mod in mods:
        fid = mod.get("file_id", "")
        version = mod.get("version", "")
        api_name = mod.get("file_name", "")
        optional = mod.get("optional", False)
        if not fid or not api_name:
            continue
        entry = data.get(fid)

        # Migrate optional mod old files from root to Optional/
        if optional and isinstance(entry, (str, dict)):
            old_name = entry if isinstance(entry, str) else entry.get("name", "")
            old_path = collection_dir / old_name
            new_path = optional_dir / old_name
            if old_path.exists() and old_path.resolve() != new_path.resolve():
                optional_dir.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
                migrated += 1

        if isinstance(entry, str):
            best_name = _resolve_name(entry, api_name, collection_dir, optional)
            data[fid] = {"name": best_name, "version": version, "optional": optional, "mod_id": mod.get("id", ""), "file_title": mod.get("file_name", "")}
            updated += 1
        elif isinstance(entry, dict):
            # Update version + optional flag + file_title from API, preserve local filename when possible
            changed = False
            if entry.get("version") != version:
                data[fid]["version"] = version
                changed = True
            if entry.get("optional") != optional:
                data[fid]["optional"] = optional
                changed = True
            if "file_title" not in entry:
                data[fid]["file_title"] = mod.get("file_name", "")
                changed = True
            if changed:
                updated += 1
            # Fix entries where name was incorrectly set to the file_id
            if entry.get("name") == fid:
                best_name = api_name if (_mod_dir(collection_dir, optional) / api_name).exists() else api_name
                data[fid]["name"] = best_name
                updated += 1
    if updated or migrated:
        manifest_path.write_text(json.dumps(data, indent=2))
        parts = []
        if updated:
            parts.append(f"updated {updated} entries")
        if migrated:
            parts.append(f"migrated {migrated} optional mods")
        print(f"  \U0001f4dd {', '.join(parts)}")


def _mod_dir(collection_dir: Path, optional: bool) -> Path:
    return collection_dir / "Optional" if optional else collection_dir


def _resolve_name(old: str, api_name: str, collection_dir: Path, optional: bool = False) -> str:
    """Pick the correct filename when upgrading old format: prefer locally-existing files."""
    base = _mod_dir(collection_dir, optional)
    if (base / old).exists():
        return old
    if (base / api_name).exists():
        return api_name
    matches = list(base.glob(f"{old}*"))
    if len(matches) == 1 and matches[0].is_file():
        return matches[0].name
    return api_name


def download_mod(mod: dict, collection_dir: Path, progress: str = "", game_id: str | None = None, game_domain: str | None = None, game_dir: Path | None = None) -> str:
    """Download a single mod file. Returns 'success' | 'skipped' | 'updated' | 'failed'."""
    if game_id is None:
        game_id = str(config_get("game_id"))
    if game_domain is None:
        game_domain = config_get("game_domain")

    name = mod["name"]
    file_name = mod.get("file_name", "")
    mod_id = mod["id"]
    file_id = mod.get("file_id", "")
    version = mod.get("version", "")
    optional = mod.get("optional", False)

    if not file_id:
        print(f"  {progress}⚠ {name} — no file_id, skipping")
        return "skipped"

    target_dir = _mod_dir(collection_dir, optional)
    target_dir.mkdir(parents=True, exist_ok=True)

    status = check_mod_status(mod, collection_dir)

    if status == "ok":
        if game_dir:
            _extract_cached(collection_dir, file_id, optional, game_dir, name)
        print(f"  {progress}⏭ {name} — up to date")
        return "skipped"

    if status == "outdated":
        print(f"  {progress}\U0001f504 {name} — update available")

    if status == "missing":
        existing = _find_global(file_id, version)
        if existing:
            target = target_dir / existing.name
            if existing.resolve() == target.resolve():
                # Already in the target directory, just record it
                _record_downloaded(file_id, existing.name, version, collection_dir, optional, mod_id=mod_id, file_title=file_name)
                _cleanup_same_mod(collection_dir, mod_id, keep=file_id, file_title=file_name)
                if game_dir:
                    _maybe_extract(target, game_dir, name)
                return "success"
            shutil.copy2(existing, target)
            print(f"  {progress}\U0001f4cb {name} (copied from other collection)")
            _record_downloaded(file_id, existing.name, version, collection_dir, optional, mod_id=mod_id, file_title=file_name)
            _cleanup_same_mod(collection_dir, mod_id, keep=file_id, file_title=file_name)
            if game_dir:
                _maybe_extract(target, game_dir, name)
            return "success"

    label = f"  {progress}\U0001f4e5 {name} [optional]" if optional else f"  {progress}\U0001f4e5 {name}"
    print(label)

    cookies = _load_cookies()
    if not cookies:
        print(f"       ❌ cookies file not found ({config_get('cookies_file')})")
        return "failed"

    try:
        with httpx.Client(cookies=cookies, timeout=httpx.Timeout(300, connect=30), follow_redirects=True) as client:
            resp = client.post(
                "https://www.nexusmods.com/Core/Libs/Common/Managers/Downloads",
                params={"GenerateDownloadUrl": ""},
                data={"game_id": game_id, "fid": file_id, "collection_id": "0"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"https://www.nexusmods.com/{game_domain}/mods/{mod_id}?tab=files&file_id={file_id}",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                },
            )
            if resp.status_code != 200:
                print(f"       ❌ failed to get download URL (HTTP {resp.status_code})")
                return "failed"

            cdn_url = resp.json().get("url", "")
            if not cdn_url:
                print(f"       ❌ no download URL returned")
                return "failed"

            filename = unquote(cdn_url.split("/")[-1].split("?")[0])
            target = target_dir / filename
            partfile = target_dir / (filename + ".part")

            for attempt in range(5):
                try:
                    headers = {}
                    resumed_from = partfile.stat().st_size if partfile.exists() else 0
                    if resumed_from > 0:
                        headers["Range"] = f"bytes={resumed_from}-"
                        print(f"       ↻ resuming at {resumed_from/1048576:.1f}MB")

                    with client.stream("GET", cdn_url, headers=headers) as resp:
                        if resp.status_code not in (200, 206):
                            print(f"       retry {attempt + 1}/5 (HTTP {resp.status_code})...")
                            time.sleep(5)
                            continue

                        total = int(resp.headers.get("content-length", 0)) + resumed_from
                        downloaded = resumed_from
                        mode = "ab" if resp.status_code == 206 else "wb"

                        with open(partfile, mode) as f:
                            for chunk in resp.iter_bytes(chunk_size=65536):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    pct = downloaded * 100 // total
                                    mb_done = downloaded / 1048576
                                    mb_total = total / 1048576
                                    print(f"\r       {pct}% {mb_done:.1f}/{mb_total:.1f}MB", end="", flush=True)
                        print()
                        break
                except Exception:
                    if attempt < 4:
                        print(f"       retry {attempt + 1}/5...")
                        time.sleep(5)
                    else:
                        raise
            else:
                if partfile.exists():
                    partfile.unlink()
                print(f"       ❌ download failed")
                return "failed"

            partfile.rename(target)
            size_kb = target.stat().st_size // 1024
            print(f"       ✅ {filename} ({size_kb}KB)")

    except Exception as e:
        print(f"       ❌ {e}")
        return "failed"

    _record_downloaded(file_id, filename, version, collection_dir, optional, mod_id=mod_id, file_title=file_name)
    # Remove any other entries for the same mod (matching mod_id + file_title)
    _cleanup_same_mod(collection_dir, mod_id, keep=file_id, file_title=file_name)
    if game_dir:
        _maybe_extract(target, game_dir, name)
    return "updated" if status == "outdated" else "success"


def _maybe_extract(zip_path: Path, game_dir: Path, name: str):
    """Extract zip to game Mods dir. Config presets and skip_extract mods are skipped."""
    skip_list = config_get("skip_extract")
    if name in skip_list:
        print(f"       ⏭ skip extract (in skip_extract)")
        return
    try:
        if _is_config_preset(zip_path):
            return
        extract_mod(zip_path, game_dir)
        print(f"       \U0001f4e6 extracted")
    except Exception:
        pass


def _extract_cached(collection_dir: Path, file_id: str, optional: bool, game_dir: Path, name: str):
    """Ensure a previously-downloaded zip is extracted to game dir (skips if already present)."""
    manifest_path = collection_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return
    data = json.loads(manifest_path.read_text())
    entry = data.get(file_id)
    if not entry:
        return
    zip_name = entry.get("name") if isinstance(entry, dict) else entry
    if not zip_name:
        return
    zip_path = _mod_dir(collection_dir, optional) / zip_name
    if not zip_path.exists():
        return
    # Only extract if the mod folder doesn't already exist in game dir
    names = _list_archive(zip_path)
    top_dirs = {n.split("/")[0] for n in names if "/" in n and n.split("/")[0]}
    already = all((game_dir / d).exists() for d in top_dirs) if top_dirs else False
    if not already:
        _maybe_extract(zip_path, game_dir, name)


def _find_global(file_id: str, version: str) -> Path | None:
    """Search all collections under data_dir for an already-downloaded file with the same version."""
    data_dir = Path(config_get("data_dir")).expanduser()
    if not data_dir.exists():
        return None
    for manifest_path in data_dir.glob(f"*/{MANIFEST_FILE}"):
        manifest = json.loads(manifest_path.read_text())
        if not isinstance(manifest, dict) or file_id not in manifest:
            continue
        entry = manifest[file_id]
        if isinstance(entry, str):
            continue
        if entry.get("version") != version:
            continue
        fname = entry.get("name", "")
        # Check both root and Optional/ subdirectory
        base = manifest_path.parent
        for sub in ["", "Optional"]:
            target = base / sub / fname if sub else base / fname
            if target.exists():
                return target
    return None


def _load_cookies() -> dict:
    cookies_file = Path(config_get("cookies_file"))
    if not cookies_file.exists():
        return {}
    cookies_data = json.loads(cookies_file.read_text())
    return {c["name"]: c["value"] for c in cookies_data}


def check_mod_status(mod: dict, collection_dir: Path) -> str:
    """Check download status. Returns 'missing' | 'outdated' | 'ok'."""
    file_id = mod.get("file_id", "")
    version = mod.get("version", "")
    if not file_id:
        return "missing"

    manifest_path = collection_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return "missing"

    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict) or file_id not in data:
        return "missing"

    entry = data[file_id]
    if isinstance(entry, str):
        return "outdated"

    if entry.get("version") != version:
        return "outdated"

    fname = entry.get("name", "")
    if not fname:
        return "missing"

    optional = entry.get("optional", False)
    if not (_mod_dir(collection_dir, optional) / fname).exists():
        return "missing"

    return "ok"


def _record_downloaded(file_id: str, filename: str, version: str, collection_dir: Path, optional: bool = False, mod_id: str = "", file_title: str = ""):
    """Record file_id -> {name, version, optional, mod_id, file_title} mapping."""
    manifest = collection_dir / MANIFEST_FILE
    if manifest.exists():
        data = json.loads(manifest.read_text())
        if isinstance(data, list):
            data = {}
    else:
        data = {}
    data[file_id] = {"name": filename, "version": version, "optional": optional, "mod_id": mod_id, "file_title": file_title}
    manifest.write_text(json.dumps(data, indent=2))


def _cleanup_same_mod(collection_dir: Path, mod_id: str, keep: str, file_title: str = ""):
    """Remove manifest entries and files for the same mod (matching mod_id + file_title) except the one being kept."""
    if not mod_id:
        return
    manifest_path = collection_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict):
        return
    changed = False
    for fid, entry in list(data.items()):
        if fid == keep:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("mod_id") != mod_id:
            continue
        # Only clean up if file_title matches (same actual mod), or if the old entry
        # predates file_title and the new entry also has no file_title (backward compat).
        entry_title = entry.get("file_title", "")
        if entry_title and file_title and entry_title != file_title:
            continue
        _remove_entry_file(collection_dir, entry)
        del data[fid]
        changed = True
    if changed:
        manifest_path.write_text(json.dumps(data, indent=2))


def _remove_entry_file(collection_dir: Path, entry):
    """Delete the file referenced by a manifest entry from disk."""
    if isinstance(entry, dict):
        fname = entry.get("name", "")
        optional = entry.get("optional", False)
    else:
        fname = entry
        optional = False
    if fname:
        file_path = (_mod_dir(collection_dir, optional)) / fname
        if file_path.exists():
            file_path.unlink()


def remove_manifest_entry(collection_dir: Path, file_id: str) -> bool:
    """Remove a manifest entry and its file from disk."""
    manifest_path = collection_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return False
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict) or file_id not in data:
        return False
    _remove_entry_file(collection_dir, data[file_id])
    del data[file_id]
    manifest_path.write_text(json.dumps(data, indent=2))
    return True
