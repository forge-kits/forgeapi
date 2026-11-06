from __future__ import annotations

from pathlib import Path

#: A directory is a forgeapi project root when its ``config/`` holds one of these files.
_ANCHORS = ("project.py", "structure.py", "database.py", "auth.py")
_MAX_DEPTH = 12


def find_project_root(start: Path) -> Path | None:
    """Walk up from *start* to the nearest directory that is a forgeapi project root.

    Returns ``None`` when *start* and its parents (up to ``_MAX_DEPTH`` levels) hold no
    ``config/`` directory with one of the anchor files.
    """
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for _ in range(_MAX_DEPTH):
        config_dir = current / "config"
        if config_dir.is_dir() and any((config_dir / name).exists() for name in _ANCHORS):
            return current
        if current.parent == current:
            break
        current = current.parent
    return None
