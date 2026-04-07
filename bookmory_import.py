"""
bookmory_import.py — convert a .bookmory file into our library format.

A .bookmory file is a ZIP archive containing a SQLite database (new_bookmory.db
or bookmory.db) with a key-value store in the `entry` table.

Field mapping:
  Bookmory status → our status
    DONE        → finished
    READING     → reading
    PAUSE       → paused
    NOT_STARTED → planned
    WISH        → planned

Language detection: Bookmory stores language as an empty string for most books,
so we detect it from the title + description text using our language module.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import language as lang_module


# ─────────────────────────────────────────────────────────────
# Status mapping
# ─────────────────────────────────────────────────────────────

_STATUS_MAP = {
    "DONE":        "finished",
    "READING":     "reading",
    "PAUSE":       "paused",
    "NOT_STARTED": "planned",
    "WISH":        "planned",
}


def _ms_to_date(ms: int | None) -> str:
    """Convert millisecond timestamp to ISO date string, or empty string."""
    if not ms or ms <= 0 or ms >= 8_000_000_000_000:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _detect_language(title: str, description: str) -> tuple[str, str]:
    """Detect language from title + description. Returns (lang_code, lang_name)."""
    text = f"{title} {description}"
    result = lang_module.detect(text)
    if result.lang == "unknown":
        # Try with just enough repeated text to get a better signal
        result = lang_module.detect(text * 3)
    return result.lang, result.lang_name


def _open_db(bookmory_path: Path) -> sqlite3.Connection:
    """Extract the SQLite DB from the .bookmory ZIP and open it in memory."""
    with zipfile.ZipFile(bookmory_path, "r") as zf:
        names = zf.namelist()
        # Prefer new_bookmory.db, fall back to bookmory.db
        db_name = next(
            (n for n in names if n == "new_bookmory.db"),
            next((n for n in names if n.endswith(".db") and "journal" not in n), None),
        )
        if db_name is None:
            raise ValueError("No SQLite database found inside .bookmory file.")
        db_bytes = zf.read(db_name)

    # Write to a temp file (sqlite3 can't open from bytes directly)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.write(db_bytes)
    tmp.flush()
    tmp_path = tmp.name
    tmp.close()
    try:
        con = sqlite3.connect(tmp_path)
        # Load everything into memory so we can delete the temp file
        mem_con = sqlite3.connect(":memory:")
        for line in con.iterdump():
            mem_con.execute(line)
        con.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return mem_con


def _load_books(con: sqlite3.Connection) -> list[dict]:
    cur = con.cursor()
    rows = cur.execute(
        "SELECT key, value FROM entry WHERE store='books' AND deleted IS NULL"
    ).fetchall()
    books = []
    for key, value_str in rows:
        try:
            books.append((key, json.loads(value_str)))
        except json.JSONDecodeError:
            continue
    return books


# ─────────────────────────────────────────────────────────────
# Main conversion
# ─────────────────────────────────────────────────────────────

def convert(bookmory_path: Path) -> list[dict]:
    """Parse a .bookmory file and return a list of library book records."""
    con = _open_db(bookmory_path)
    raw_books = _load_books(con)
    con.close()

    result = []
    for bkey, b in raw_books:
        title = (b.get("title") or "").strip()
        if not title:
            continue

        # Status
        status_list = b.get("status_list") or []
        raw_status = status_list[-1] if status_list else "NOT_STARTED"
        status = _STATUS_MAP.get(raw_status, "planned")

        # Dates from reads list
        reads = b.get("reads") or []
        date_started  = ""
        date_finished = ""
        if reads:
            start_ms = reads[0].get("start")
            date_started = _ms_to_date(start_ms)
            # finished date: last read's end, or first_read_done_date
            end_ms = reads[-1].get("end") or b.get("last_read_done_date")
            date_finished = _ms_to_date(end_ms) if status == "finished" else ""

        # Fall back to top-level date fields
        if not date_started:
            date_started = _ms_to_date(b.get("first_read_start_date"))
        if not date_finished and status == "finished":
            date_finished = _ms_to_date(b.get("last_read_done_date"))

        # Date added
        date_added = _ms_to_date(b.get("created_at")) or datetime.now().strftime("%Y-%m-%d")

        # Pages (stored as float in bookmory)
        pages = int(b.get("total_page") or b.get("real_total_page") or 0)

        # Language detection
        description = b.get("description") or ""
        lang_code, lang_name = _detect_language(title, description)

        # Build a unique ID from the bookmory key (it's already a timestamp string)
        try:
            book_id = int(bkey)
        except (ValueError, TypeError):
            import time
            book_id = int(time.time() * 1000)

        record = {
            "id":           book_id,
            "title":        title,
            "author":       ", ".join(b.get("authors") or [b.get("author", "")]),
            "lang":         lang_code,
            "lang_name":    lang_name,
            "pages":        pages,
            "words":        0,           # unknown — user can fill in
            "difficulty":   None,        # unknown — user can fill in
            "scores":       {},
            "tags":         [],
            "status":       status,
            "dateAdded":    date_added,
            "dateStarted":  date_started,
            "dateFinished": date_finished,
            "source":       "bookmory",
        }
        result.append(record)

    return result
