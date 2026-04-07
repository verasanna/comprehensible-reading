"""
extraction.py — text extraction from .epub and .pdf files.

Supports:
  - EPUB via ebooklib
  - PDF via PyMuPDF (fitz)

All extractors return (text, title, author).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# EPUB metadata (reads OPF directly — no ebooklib needed)
# ─────────────────────────────────────────────────────────────

def _read_opf_metadata(path: Path) -> dict:
    """Return {title, author} from the OPF metadata inside an EPUB ZIP."""
    result = {"title": "", "author": ""}
    try:
        with zipfile.ZipFile(path) as z:
            container = z.read("META-INF/container.xml").decode("utf-8", errors="replace")
            m = re.search(r'full-path="([^"]+\.opf)"', container)
            if not m:
                return result
            opf = z.read(m.group(1)).decode("utf-8", errors="replace")
            t = re.search(r"<dc:title[^>]*>([^<]+)</dc:title>", opf)
            if t:
                result["title"] = t.group(1).strip()
            c = re.search(r"<dc:creator[^>]*>([^<]+)</dc:creator>", opf)
            if c:
                result["author"] = c.group(1).strip()
    except Exception:
        pass
    return result


# ─────────────────────────────────────────────────────────────
# EPUB
# ─────────────────────────────────────────────────────────────

def extract_epub(path: Path) -> tuple[str, str, str]:
    """Return (text, title, author) from an EPUB file."""
    import ebooklib
    from ebooklib import epub
    from html.parser import HTMLParser

    class _StripHTML(HTMLParser):
        def __init__(self):
            super().__init__()
            self.chunks: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "nav"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                self.chunks.append(data)

    meta = _read_opf_metadata(path)
    book  = epub.read_epub(str(path), options={"ignore_ncx": True})
    title  = meta["title"]  or book.title or path.stem
    author = meta["author"] or ""

    chunks: list[str] = []
    total = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        parser = _StripHTML()
        parser.feed(item.get_content().decode("utf-8", errors="replace"))
        chunk = " ".join(parser.chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > 600_000:
            break

    return " ".join(chunks), title, author


# ─────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────

def extract_pdf(path: Path) -> tuple[str, str, str]:
    """Return (text, title, author) from a PDF file using PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    title  = (doc.metadata.get("title")  or "").strip() or path.stem
    author = (doc.metadata.get("author") or "").strip()

    chunks: list[str] = []
    total = 0
    max_pages = min(doc.page_count, 300)

    for i in range(max_pages):
        page_text = doc[i].get_text("text")
        chunks.append(page_text)
        total += len(page_text)
        if total > 600_000:
            break

    text = " ".join(chunks)

    avg_chars = total / max(1, min(max_pages, doc.page_count))
    if avg_chars < 100 and total < 500:
        raise ValueError(
            "Very little text could be extracted from this PDF. "
            "It may be a scanned document, image-based, or encrypted. "
            "A text-based PDF is required."
        )

    return text, title, author


# ─────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────

def extract_text(path: Path) -> tuple[str, str, str]:
    """Dispatch to the correct extractor. Returns (text, title, author)."""
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return extract_epub(path)
    elif suffix == ".pdf":
        return extract_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}. Only .epub and .pdf are supported.")
