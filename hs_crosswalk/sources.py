"""The source manifest and hash-verified downloads."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "manifests" / "sources.json"
DEFAULT_CACHE = Path("data") / "sources"
MX_SUBDIR = "tigie-nico-mx"


class SourceError(RuntimeError):
    """A source could not be fetched or did not match its pinned hash."""


def manifest_path() -> Path:
    return Path(os.environ.get("HSX_MANIFEST") or DEFAULT_MANIFEST)


def cache_dir() -> Path:
    return Path(os.environ.get("HSX_CACHE_DIR") or DEFAULT_CACHE)


def request(url: str) -> urllib.request.Request:
    """A GET request. Python's own User-Agent is kept unless HSX_USER_AGENT is set:
    the USITC file host refuses some unfamiliar agents."""
    agent = os.environ.get("HSX_USER_AGENT")
    return urllib.request.Request(url, headers={"User-Agent": agent} if agent else {})


def load_manifest(path: Path | None = None) -> dict:
    with open(path or manifest_path(), encoding="utf-8") as fh:
        return json.load(fh)


def save_manifest(data: dict, path: Path | None = None) -> None:
    target = path or manifest_path()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    target.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, sha256: str | None, timeout: float = 300) -> tuple[str, int]:
    """Download ``url`` to ``dest``; refuse the file if ``sha256`` is given and differs.

    An existing ``dest`` with the expected hash is kept without a new download.
    Returns the file's sha256 and size in bytes.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if sha256 and dest.is_file() and sha256_file(dest) == sha256:
        return sha256, dest.stat().st_size
    tmp = dest.with_name(dest.name + ".part")
    req = request(url)
    h = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
            for chunk in iter(lambda: resp.read(1 << 20), b""):
                h.update(chunk)
                out.write(chunk)
                size += len(chunk)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise SourceError(f"download failed: {url}: {exc}") from exc
    digest = h.hexdigest()
    if sha256 and digest != sha256:
        tmp.unlink(missing_ok=True)
        raise SourceError(f"sha256 mismatch for {url}: expected {sha256}, got {digest}")
    tmp.replace(dest)
    return digest, size


def us_files(manifest: dict) -> dict[str, dict]:
    return manifest["us_hts"]["files"]


def mx_files(manifest: dict) -> dict[str, dict]:
    return manifest["mx_tigie"]["files"]


def mx_base_url(manifest: dict) -> str:
    return (os.environ.get("TIGIE_RELEASE_URL") or manifest["mx_tigie"]["release_url"]).rstrip("/")


def extract_members(archive: Path, members: dict[str, str], dest: Path) -> dict[str, str]:
    """Copy the named zip members to ``dest/<file name>``; nothing else is extracted.

    ``members`` maps a member path inside the zip to the file name to write.
    Returns the sha256 of each written file.
    """
    dest.mkdir(parents=True, exist_ok=True)
    digests = {}
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        for member, name in members.items():
            if member not in names:
                raise SourceError(f"{archive.name}: no member {member}")
            if "/" in name or "\\" in name or name in ("", ".", ".."):
                raise SourceError(f"refusing to write {name!r}")
            target = dest / name
            with zf.open(member) as src, open(target, "wb") as out:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    out.write(chunk)
            digests[name] = sha256_file(target)
    return digests
