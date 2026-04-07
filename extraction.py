"""
extraction.py — text extraction from .epub and .pdf files.

Supports:
  - EPUB via ebooklib
  - PDF via PyMuPDF (fitz)
"""

from __future__ import annotations

from pathlib import Path


# ─────────────────────────────────────────────────────────────
# EPUB
# ─────────────────────────────────────────────────────────────

def extract_epub(path: Path) -> tuple[str, str]:
    """Return (text, title) from an EPUB file."""
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

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    title = book.title or path.stem

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

    return " ".join(chunks), title


# ─────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────

def extract_pdf(path: Path) -> tuple[str, str]:
    """Return (text, title) from a PDF file using PyMuPDF.

    Strategy:
      1. Try standard text extraction (fitz page.get_text).
      2. If very little text is found (scanned / image-based PDF),
         raise a clear error so the user knows why it failed.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    title = (doc.metadata.get("title") or "").strip() or path.stem

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

    # Heuristic: fewer than 100 chars per page on average → likely scanned
    avg_chars = total / max(1, min(max_pages, doc.page_count))
    if avg_chars < 100 and total < 500:
        raise ValueError(
            "Very little text could be extracted from this PDF. "
            "It may be a scanned document, image-based, or encrypted. "
            "A text-based PDF is required."
        )

    return text, title


# ─────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────

def extract_text(path: Path) -> tuple[str, str]:
    """Dispatch to the correct extractor based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return extract_epub(path)
    elif suffix == ".pdf":
        return extract_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}. Only .epub and .pdf are supported.")
