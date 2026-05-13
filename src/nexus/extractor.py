import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

_RESOURCE_EXTS = {".png", ".xnb", ".tbin", ".tmx", ".wav", ".ogg", ".mp3"}


def backup_mods(game_dir: Path) -> Path | None:
    """Back up the entire Mods dir to Mods.backup.YYYY-MM-DD/. Skips if already exists today."""
    if not game_dir.exists():
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    backup_dir = game_dir.parent / f"Mods.backup.{today}"
    if backup_dir.exists():
        return None
    print(f"  Backing up Mods to {backup_dir} ...")
    shutil.copytree(game_dir, backup_dir)
    print(f"  Backup complete")
    return backup_dir


def _find_rar_tool() -> str | None:
    """Find an available RAR extraction tool on the system."""
    for cmd in ["bsdtar", "unrar", "7z", "7zz"]:
        if shutil.which(cmd):
            return cmd
    return None


def list_archive(path: Path) -> list[str]:
    """List all file paths inside an archive. Supports zip / 7z / rar."""
    ext = path.suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(path) as z:
            return z.namelist()
    if ext == ".7z":
        import py7zr
        with py7zr.SevenZipFile(path) as sz:
            return sz.getnames()
    # .rar — find external tool
    tool = _find_rar_tool()
    if not tool:
        raise RuntimeError("No RAR extraction tool found (need bsdtar / unrar / 7z)")
    if tool in ("7z", "7zz"):
        r = subprocess.run([tool, "l", "-ba", str(path)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{tool} failed to read: {path}")
        lines = []
        for line in r.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 6:
                lines.append(" ".join(parts[5:]))
        return lines
    # bsdtar / unrar
    r = subprocess.run([tool, "-tf", str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{tool} failed to read: {path}")
    return [line for line in r.stdout.strip().split("\n") if line]


def _extract_archive(path: Path, dest: Path):
    """Extract archive to destination. Supports zip / 7z / rar."""
    ext = path.suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)
        return
    if ext == ".7z":
        import py7zr
        dest.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(path) as sz:
            sz.extractall(dest)
        return
    # .rar
    tool = _find_rar_tool()
    if not tool:
        raise RuntimeError("No RAR extraction tool found")
    dest.mkdir(parents=True, exist_ok=True)
    if tool in ("7z", "7zz"):
        subprocess.run([tool, "x", f"-o{dest}", str(path)], check=True, capture_output=True)
    else:
        subprocess.run([tool, "-xf", str(path), "-C", str(dest)], check=True, capture_output=True)


def _open_archive(path: Path, filename: str) -> bytes:
    """Read a single file from an archive."""
    ext = path.suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(path) as z:
            return z.read(filename)
    if ext == ".7z":
        import py7zr
        with py7zr.SevenZipFile(path) as sz:
            data = sz.read([filename])
            return data[filename]
    # .rar — extract single file to temp dir
    tool = _find_rar_tool()
    if not tool:
        raise RuntimeError("No RAR extraction tool found")
    with tempfile.TemporaryDirectory() as tmp:
        if tool in ("7z", "7zz"):
            subprocess.run([tool, "x", f"-o{tmp}", str(path), filename],
                           check=True, capture_output=True)
        else:
            subprocess.run([tool, "-xf", str(path), "-C", tmp, filename],
                           check=True, capture_output=True)
        return (Path(tmp) / filename).read_bytes()


def is_config_preset(path: Path) -> bool:
    """Check if archive is a config preset: no dll, no resource files, only json."""
    try:
        names = list_archive(path)
    except Exception:
        return False
    has_config = False
    for n in names:
        if n.endswith("/") or n.endswith("\\"):
            continue
        ext = Path(n).suffix.lower()
        if ext == ".dll":
            return False
        if ext in _RESOURCE_EXTS:
            return False
        if ext != ".json":
            return False
        if n.endswith("config.json"):
            has_config = True
    return has_config


def extract_mod(zip_path: Path, game_dir: Path) -> str:
    """Extract a mod archive to game Mods dir, cleaning old folders first."""
    names = list_archive(zip_path)
    top_dirs: set[str] = set()
    for n in names:
        # Normalize path separators (Windows 7z may output \\)
        parts = n.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0]:
            top_dirs.add(parts[0])
    for d in top_dirs:
        old_dir = game_dir / d
        if old_dir.exists():
            shutil.rmtree(old_dir)
    _extract_archive(zip_path, game_dir)
    return "extracted"


def route_configs(zip_path: Path, game_dir: Path) -> list[str]:
    """Route config.json files to game dir using the exact paths from the zip."""
    routed = []
    names = list_archive(zip_path)

    for n in names:
        if n.endswith("/") or n.endswith("\\"):
            continue
        if not n.endswith("config.json"):
            continue
        rel = n.replace("\\", "/")
        target = game_dir / rel
        if not target.parent.is_dir():
            print(f"     ⚠ directory not found: {target.parent}, skipping")
            continue
        target.write_bytes(_open_archive(zip_path, n))
        routed.append(rel.split("/")[0])

    return routed


def route_all_configs(collection_dir: Path, game_dir: Path):
    """Scan collection dir for config presets and route them all."""
    for zip_path in collection_dir.glob("*.zip"):
        try:
            if is_config_preset(zip_path):
                route_configs(zip_path, game_dir)
        except Exception as e:
            print(f"     ⚠ config routing failed for {zip_path.name}: {e}")
    opt_dir = collection_dir / "Optional"
    if opt_dir.exists():
        for zip_path in opt_dir.glob("*.zip"):
            try:
                if is_config_preset(zip_path):
                    route_configs(zip_path, game_dir)
            except Exception as e:
                print(f"     ⚠ config routing failed for {zip_path.name}: {e}")


