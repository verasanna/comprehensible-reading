"""
library.py — local persistence for books and tags.

Everything is stored as plain JSON files in the project directory:
  - library.json  : list of book records
  - tags.json     : list of tag definitions
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
LIBRARY_FILE = BASE_DIR / "library.json"
TAGS_FILE = BASE_DIR / "tags.json"


# ─────────────────────────────────────────────────────────────
# Books
# ─────────────────────────────────────────────────────────────

def load() -> list[dict]:
    """Load the book library from disk."""
    if LIBRARY_FILE.exists():
        try:
            return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save(books: list[dict]) -> None:
    """Persist the book library to disk."""
    LIBRARY_FILE.write_text(
        json.dumps(books, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────
# Tags
# ─────────────────────────────────────────────────────────────

def load_tags() -> list[dict]:
    """Load tag definitions from disk.

    Each tag: { name, color, showInStats }
    """
    if TAGS_FILE.exists():
        try:
            return json.loads(TAGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_tags(tags: list[dict]) -> None:
    """Persist tag definitions to disk."""
    TAGS_FILE.write_text(
        json.dumps(tags, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
