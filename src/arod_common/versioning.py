"""Revision and version metadata helpers.

The helpers in this module are intentionally lightweight and safe to call in
runtime environments where the Git CLI may be unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import platform
import socket
import subprocess
from typing import Any, Dict, Optional


DEFAULT_DIST_NAME = "athena-rods"


def _find_project_root(start_path: Optional[Path] = None) -> Path:
    """Locate the nearest parent directory that contains ``.git``.

    Parameters
    ----------
    start_path:
        Optional starting path. Defaults to the current working directory.

    Returns
    -------
    Path
        Project root if found, otherwise ``start_path`` (or CWD).
    """
    current = (start_path or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    """Run a Git command and return stripped stdout on success."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def get_package_version(dist_name: str = DEFAULT_DIST_NAME) -> str:
    """Return installed package version if available, else ``"unknown"``."""
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return "unknown"


def get_git_revision(project_root: Optional[Path] = None, short: bool = True) -> str:
    """Return Git commit revision string.

    Returns ``"unknown"`` when the repository or Git metadata is unavailable.
    """
    root = _find_project_root(project_root)
    args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
    revision = _run_git(args, cwd=root)
    return revision if revision else "unknown"


def is_git_dirty(project_root: Optional[Path] = None) -> Optional[bool]:
    """Return Git dirty state, or ``None`` when unavailable."""
    root = _find_project_root(project_root)
    result = _run_git(["status", "--porcelain"], cwd=root)
    if result is None:
        return None
    return bool(result)


def build_revision_record(
    dist_name: str = DEFAULT_DIST_NAME,
    project_root: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standard revision metadata record.

    Parameters
    ----------
    dist_name:
        Python distribution name used for installed-version lookup.
    project_root:
        Optional repository root override.
    extra:
        Optional additional key-value metadata.

    Returns
    -------
    dict
        Structured revision/build metadata.
    """
    root = _find_project_root(project_root)
    record: Dict[str, Any] = {
        "project": "athena-rods",
        "version": get_package_version(dist_name=dist_name),
        "git_revision": get_git_revision(project_root=root, short=True),
        "git_dirty": is_git_dirty(project_root=root),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "project_root": str(root),
    }
    if extra:
        record.update(extra)
    return record


def write_revision_manifest(
    output_path: Path,
    dist_name: str = DEFAULT_DIST_NAME,
    project_root: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write revision metadata to JSON and return the record."""
    import json

    record = build_revision_record(
        dist_name=dist_name,
        project_root=project_root,
        extra=extra,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
