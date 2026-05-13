"""Nexus Mods GraphQL API for collection metadata — no browser required."""

import re
import time as _time

import httpx

from nexus.config import get as config_get

GRAPHQL_URL = "https://api-router.nexusmods.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def parse_collection(collection_url: str) -> tuple[str, list[dict]]:
    """Fetch collection data via API. Returns (collection_name, mods)."""
    slug = _extract_slug(collection_url)
    game = _extract_game(collection_url)

    print(f"\nFetching collection... (slug: {slug}, game: {game})")

    query = """
    query($slug: String!, $domain: String) {
      collection(slug: $slug, viewAdultContent: true, domainName: $domain) {
        name
        latestPublishedRevision {
          modCount
          modFiles {
            fileId
            version
            optional
            file {
              name
              modId
              fileId
              sizeInBytes
              version
              uid
              mod {
                modId
                name
                uploader { name }
              }
            }
          }
        }
      }
    }
    """

    for attempt in range(5):
        try:
            r = httpx.post(
                GRAPHQL_URL,
                json={"query": query, "variables": {"slug": slug, "domain": game}},
                headers=HEADERS,
                timeout=30,
            )
            data = r.json()
            break
        except Exception as e:
            if attempt < 4:
                print(f"  API request failed, retry {attempt + 1}/5... ({e})")
                _time.sleep(3)
            else:
                raise

    if "errors" in data:
        msgs = [e.get("message", "") for e in data["errors"]]
        raise RuntimeError(f"GraphQL error: {', '.join(msgs)}")
    collection = data["data"]["collection"]
    name = collection["name"]
    revision = collection["latestPublishedRevision"]
    mod_files = revision["modFiles"]

    mods = []
    for mf in mod_files:
        f = mf.get("file") or {}
        mod = f.get("mod") or {}
        mods.append({
            "id": str(f.get("modId", "")),
            "name": mod.get("name", "Unknown"),
            "uploader": (mod.get("uploader") or {}).get("name", "unknown"),
            "file_id": str(f.get("fileId", "")),
            "file_name": f.get("name", ""),
            "size_bytes": f.get("sizeInBytes", 0),
            "version": mf.get("version", f.get("version", "")),
            "optional": mf.get("optional", False),
            "url": f"https://www.nexusmods.com/{game}/mods/{f.get('modId', '')}",
        })

    print(f"Collection: {name}")
    print(f"Found {len(mods)} mods")
    for i, m in enumerate(mods, 1):
        opt = " (optional)" if m["optional"] else ""
        print(f"  [{i}] {m['name']}{opt} — {m['uploader']}")

    return name, mods


def _extract_slug(url: str) -> str:
    match = re.search(r"/collections/(\w+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract collection slug from URL: {url}")


def _normalize_title(t: str) -> str:
    """Strip trailing version suffix like '- v2.8.26' to help match file titles across versions."""
    t = re.sub(r"\s*\(\d[\d.]*\)$", "", t)       # Skip or Socialize (0.0.6)
    t = re.sub(r"\s*[-–]\s*v?\d[\d.]*$", "", t)  # UI Info Suite - v2.8.26
    return t.strip()


def fetch_latest_versions(mods: list[dict], game_id: int | None = None) -> dict[tuple, dict]:
    """Batch-query the latest file matching each mod's file_name.
    Returns {(mod_id, file_name): {file_id, file_name, version}}."""
    if game_id is None:
        game_id = config_get("game_id")

    if not mods:
        return {}

    skip_keywords = ["demo pack", "android", "-alpha", "-beta", "-dev", "hotfix"]
    results: dict[tuple, dict] = {}
    batch_size = 10

    for i in range(0, len(mods), batch_size):
        batch = mods[i:i + batch_size]
        aliases = []
        for j, mod in enumerate(batch):
            mod_id = mod["id"]
            aliases.append(
                f"m{j}: modFiles(gameId: {game_id}, modId: {mod_id}) {{"
                f"  fileId name version "
                f"}}"
            )

        query = "query {" + " ".join(aliases) + "}"

        for attempt in range(5):
            try:
                r = httpx.post(
                    GRAPHQL_URL,
                    json={"query": query},
                    headers=HEADERS,
                    timeout=30,
                )
                data = r.json()
                break
            except Exception:
                if attempt < 4:
                    _time.sleep(3)
                else:
                    data = None
                    break

        if data is None:
            if i + batch_size < len(mods):
                _time.sleep(0.5)
            continue

        for j, mod in enumerate(batch):
            key = f"m{j}"
            files = data.get("data", {}).get(key)
            if not files:
                continue

            mod_id = mod["id"]
            target_name = mod.get("file_name", "")
            target_norm = _normalize_title(target_name)

            # Filter to non-auxiliary files, sorted newest first
            candidates = []
            for f in reversed(files):
                name_lower = f.get("name", "").lower()
                if any(kw in name_lower for kw in skip_keywords):
                    continue
                candidates.append(f)

            if not candidates:
                continue

            # Try exact file_name match first
            found = None
            for f in candidates:
                if f.get("name", "") == target_name:
                    found = f
                    break

            # Try normalized match
            if not found and target_norm:
                for f in candidates:
                    if _normalize_title(f.get("name", "")) == target_norm:
                        found = f
                        break

            # Fallback: most recent non-auxiliary file
            if not found:
                found = candidates[0]

            results[(mod_id, target_name)] = {
                "file_id": str(found.get("fileId", "")),
                "file_name": found.get("name", ""),
                "version": found.get("version", ""),
            }

        if i + batch_size < len(mods):
            _time.sleep(0.5)

    return results


def _extract_game(url: str) -> str:
    match = re.search(r"/games/(\w+)", url)
    if match:
        return match.group(1)
    # Fallback: extract from /stardewvalley/ pattern
    match = re.search(r"nexusmods\.com/(\w+)/", url)
    if match:
        return match.group(1)
    return config_get("game_domain")
