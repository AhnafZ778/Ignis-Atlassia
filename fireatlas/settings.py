"""Local server settings. Secrets never enter browser responses or exports."""

import os
from pathlib import Path


def firms_key():
    """Environment overrides an owner-managed credential outside the repository."""
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if key:
        return key
    path = Path(os.environ.get("FIRMS_KEY_FILE", str(Path.home() / ".config/fireatlas/firms.key")))
    try:
        return path.read_text().strip() or None
    except FileNotFoundError:
        return None
