"""Self-update for the desktop exe: find a newer GitHub release, download and verify it, stage it for the swap."""
import hashlib
import os
import zipfile
from pathlib import Path

import httpx

DEFAULT_REPO = "Furqanali111/ZCS-LEADENGINE"


def parse(v: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(p) for p in v.lstrip("vV").split("."))
    except ValueError:
        return None  # "dev" and other non-numeric versions never update


def is_newer(latest: str, current: str) -> bool:
    a, b = parse(latest), parse(current)
    return a is not None and b is not None and a > b


def _headers(token: str | None, accept: str = "application/vnd.github+json") -> dict:
    h = {"Accept": accept, "User-Agent": "zcs-leadengine-updater"}
    if token:  # private repo: a read-only fine-grained token in .env as ZCS_UPDATE_TOKEN
        h["Authorization"] = f"Bearer {token}"
    return h


def latest_release(repo: str, token: str | None = None) -> dict | None:
    r = httpx.get(f"https://api.github.com/repos/{repo}/releases/latest", headers=_headers(token), timeout=5)
    return r.json() if r.status_code == 200 else None


def stage_update(release: dict, dest: Path, token: str | None = None) -> bool:
    """Download the release zip into dest (a fresh folder). False if there is no usable zip or the checksum fails."""
    asset = next((a for a in release.get("assets", []) if a["name"].endswith(".zip")), None)
    if not asset:
        return False
    r = httpx.get(asset["url"], headers=_headers(token, "application/octet-stream"), timeout=120, follow_redirects=True)
    r.raise_for_status()
    digest = (asset.get("digest") or "").removeprefix("sha256:")
    if digest and hashlib.sha256(r.content).hexdigest() != digest:
        return False
    dest.mkdir(parents=True, exist_ok=True)
    zpath = dest / "update.zip"
    zpath.write_bytes(r.content)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    zpath.unlink()
    return True


def apply_script(install_dir: Path, exe_name: str) -> Path:
    """A batch file that waits for this process to exit, copies the new files over the old (never .env), restarts."""
    bat = install_dir / "apply_update.bat"
    bat.write_text(
        "@echo off\r\n"
        "ping -n 4 127.0.0.1 >nul\r\n"  # about 3 seconds for this process to exit
        'xcopy /E /Y /Q "_update\\zcs-leadengine\\*" "." >nul\r\n'
        'rmdir /S /Q "_update"\r\n'
        f'start "" "{exe_name}"\r\n'
    )
    return bat


def token_from_env() -> str | None:
    return os.environ.get("ZCS_UPDATE_TOKEN") or None
