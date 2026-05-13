import json
import re
import sys
from pathlib import Path

from nexus.collection import parse_collection, fetch_latest_versions
from nexus.config import get as config_get
from nexus.downloader import (
    download_mod, sync_manifest, remove_manifest_entry,
    STATUS_SUCCESS, STATUS_UPDATED, STATUS_SKIPPED, STATUS_FAILED,
)
from nexus.extractor import backup_mods, route_all_configs
from nexus.modslist import add as modslist_add, load as modslist_load

GAME_DIR = Path(config_get("game_dir")).expanduser()
DATA_DIR = Path(config_get("data_dir")).expanduser()


def _normalize_url(url: str) -> str:
    """Normalize collection URL to canonical form (always ends with /mods)."""
    url = re.sub(r"/(modsupdate|revision|track)$", "/mods", url)
    if not url.endswith("/mods"):
        url = re.sub(r"/?$", "/mods", url)
    return url


def sanitize_dirname(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[/\\:*?\"<>|]", "-", name)
    name = re.sub(r"\s+", " ", name)
    return name[:100]


def download_collection(collection_name: str, mods: list[dict], game_dir: Path | None = None) -> tuple[int, int, int, int]:
    """Download all mods in a collection. Returns (new, updated, skipped, failed)."""
    collection_dir = DATA_DIR / sanitize_dirname(collection_name)
    collection_dir.mkdir(parents=True, exist_ok=True)

    sync_manifest(mods, collection_dir)

    total = len(mods)
    print(f"\n{total} mods → {collection_dir}")
    if game_dir:
        print(f"Install to: {game_dir}")
    print("-" * 60)

    success = 0
    updated = 0
    failed = 0
    skipped = 0

    try:
        for i, mod in enumerate(mods, 1):
            progress = f"[{i}/{total}] "
            result = download_mod(mod, collection_dir, progress, game_dir=game_dir)
            if result == STATUS_SUCCESS:
                success += 1
            elif result == STATUS_UPDATED:
                updated += 1
            elif result == STATUS_SKIPPED:
                skipped += 1
            else:
                failed += 1
    except KeyboardInterrupt:
        print("\n\nCancelled")
        failed = total - success - updated - skipped

    if game_dir:
        route_all_configs(collection_dir, game_dir)

    print("-" * 60)
    print(f"  {collection_name}: {success} new, {updated} updated, {skipped} skipped, {failed} failed ({total} total)")
    return success, updated, skipped, failed


def cmd_download(url: str):
    """Download collection zips only, no extraction. Registers in mods_list."""
    print("=" * 60)
    print("Nexus Mods Collection Downloader — Download")
    print("=" * 60)

    url = _normalize_url(url)
    collection_name, mods = parse_collection(url)
    download_collection(collection_name, mods)
    modslist_add(url, collection_name, installed=False)
    print(f"\nAdded to mods_list: {collection_name}")


def cmd_install(url: str):
    """Full install: backup → download → extract → config routing."""
    print("=" * 60)
    print("Nexus Mods Collection Downloader — Install")
    print("=" * 60)

    url = _normalize_url(url)
    backup_mods(GAME_DIR)

    collection_name, mods = parse_collection(url)
    download_collection(collection_name, mods, game_dir=GAME_DIR)
    modslist_add(url, collection_name, installed=True)
    print(f"\nAdded to mods_list: {collection_name}")


def _update_collection(url: str, entry: dict):
    """Update a single collection. Returns (success, updated, skipped, failed)."""
    is_installed = entry.get("installed", False)
    label = "install" if is_installed else "download"
    print(f"\nCollection: {entry['name']} [{label}]")
    if is_installed:
        backup_mods(GAME_DIR)
    game_dir = GAME_DIR if is_installed else None

    collection_name, mods = parse_collection(url)
    print(f"  Checking latest versions...")
    latest_map = fetch_latest_versions(mods)
    overridden = 0
    collection_dir = DATA_DIR / sanitize_dirname(collection_name)
    for mod in mods:
        latest = latest_map.get((mod["id"], mod.get("file_name", "")))
        if latest and latest["version"] != mod["version"]:
            if remove_manifest_entry(collection_dir, mod["file_id"]):
                print(f"  🗑 {mod['name']} (old version)")
            mod["file_id"] = latest["file_id"]
            mod["file_name"] = latest["file_name"]
            mod["version"] = latest["version"]
            overridden += 1
    if overridden:
        print(f"  {overridden} mod(s) have newer versions")

    s, u, sk, f = download_collection(collection_name, mods, game_dir=game_dir)
    modslist_add(url, collection_name, installed=is_installed)
    return s, u, sk, f


def cmd_update():
    """Update all installed collections: backup → download latest → extract → config routing."""
    mods_list = modslist_load()
    if not mods_list:
        print("mods_list.json is empty. Use install or download first.")
        sys.exit(0)

    urls = list(mods_list.keys())
    print("=" * 60)
    print(f"Nexus Mods Collection Downloader — Update ({len(urls)} collections)")
    print("=" * 60)

    total_success = 0
    total_updated = 0
    total_skipped = 0
    total_failed = 0

    for url in urls:
        try:
            s, u, sk, f = _update_collection(url, mods_list[url])
            total_success += s
            total_updated += u
            total_skipped += sk
            total_failed += f
        except KeyboardInterrupt:
            print("\nCancelled")
            break
        except Exception as e:
            print(f"  ❌ collection failed: {e}")
            total_failed += 1

    print("\n" + "=" * 60)
    print(f"All done: {total_success} new, {total_updated} updated, {total_skipped} skipped, {total_failed} failed")


def cmd_login():
    """Read Nexus Mods cookies from browser and save to cookies file."""
    try:
        import browser_cookie3
    except ImportError:
        print("browser-cookie3 is required: pip install browser-cookie3")
        sys.exit(1)

    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Firefox", browser_cookie3.firefox),
        ("Safari", browser_cookie3.safari),
        ("Chromium", browser_cookie3.chromium),
        ("Brave", browser_cookie3.brave),
        ("Edge", browser_cookie3.edge),
    ]

    required = ["nexusmods_session", "__cf_bm", "cf_clearance"]

    for name, fn in browsers:
        try:
            cj = fn(domain_name="nexusmods.com")
            cookies = list(cj)
            if cookies:
                data = [{"name": c.name, "value": c.value} for c in cookies]
                found = {c["name"] for c in data}
                missing = [n for n in required if n not in found]
                if not missing:
                    Path(config_get("cookies_file")).write_text(json.dumps(data, indent=2))
                    print(f"Got {len(data)} cookies from {name} → {config_get('cookies_file')}")
                    return
                else:
                    print(f"{name}: found {sorted(found)}, missing {missing}")
        except Exception:
            pass

    print("Could not find complete Nexus Mods cookies. Make sure you are logged in at nexusmods.com")
    sys.exit(1)


def cmd_list():
    """List collections and pick one to install."""
    mods_list = modslist_load()
    if not mods_list:
        print("mods_list.json is empty. Use install or download first.")
        sys.exit(0)

    urls = list(mods_list.keys())
    while True:
        print("=" * 60)
        print(f"Collections ({len(urls)})")
        print("=" * 60)

        for i, url in enumerate(urls, 1):
            entry = mods_list[url]
            status = "installed" if entry.get("installed", False) else "downloaded"
            print(f"\n  [{i}] {entry['name']} [{status}]")
            print(f"      {url}")

        print()
        try:
            choice = input("Number=install, u+number=update, q=quit: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice.lower() == "q":
            break

        action = "install"
        num_str = choice
        if choice.lower().startswith("u"):
            action = "update"
            num_str = choice[1:].strip()

        try:
            idx = int(num_str) - 1
            if 0 <= idx < len(urls):
                url = urls[idx]
                entry = mods_list[url]
                if action == "update":
                    _update_collection(url, entry)
                else:
                    cmd_install(urls[idx])
                break
        except ValueError:
            pass

        print(f"  Invalid: {choice}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  tasan-nexus login                       Refresh cookies from browser")
        print("  tasan-nexus list                        List collections, pick to install")
        print("  tasan-nexus download <collection_url>   Download zips only")
        print("  tasan-nexus install <collection_url>    Full install (backup → download → extract)")
        print("  tasan-nexus update                      Update all collections")
        print("  tasan-nexus <collection_url>            Same as install")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "login":
        cmd_login()
    elif arg == "list":
        cmd_list()
    elif arg == "download":
        if len(sys.argv) < 3:
            print("Usage: tasan-nexus download <collection_url>")
            sys.exit(1)
        cmd_download(sys.argv[2])
    elif arg == "update":
        cmd_update()
    elif arg == "install":
        if len(sys.argv) < 3:
            print("Usage: tasan-nexus install <collection_url>")
            sys.exit(1)
        cmd_install(sys.argv[2])
    else:
        cmd_install(arg)


if __name__ == "__main__":
    main()
