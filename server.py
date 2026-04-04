"""
server.py — Comprehensible Reading local web server.

Run with:
    uv run server.py

Or in production:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import reader as rd

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
LIBRARY_FILE = BASE_DIR / "library.json"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

jinja = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# ─────────────────────────────────────────────────────────────
# Library persistence (plain JSON, no database)
# ─────────────────────────────────────────────────────────────

def load_library() -> list[dict]:
    if LIBRARY_FILE.exists():
        try:
            return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_library(books: list[dict]) -> None:
    LIBRARY_FILE.write_text(
        json.dumps(books, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def today() -> str:
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

async def index(request: Request) -> HTMLResponse:
    template = jinja.get_template("index.html")
    return HTMLResponse(template.render())


async def api_analyse(request: Request) -> JSONResponse:
    """POST /api/analyse — accepts a multipart file upload."""
    try:
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            return JSONResponse({"error": "No file provided."}, status_code=400)

        filename: str = upload.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in (".epub", ".pdf"):
            return JSONResponse(
                {"error": "Only .epub and .pdf files are supported."},
                status_code=400,
            )

        # Write to a temp file so our reader can use Path-based APIs
        data = await upload.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        try:
            result = rd.analyse(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        return JSONResponse({
            "title": result.title,
            "stats": asdict(result.stats),
            "scores": asdict(result.scores),
            "language": asdict(result.language),
        })

    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"Processing error: {exc}"}, status_code=500)


async def api_library_get(request: Request) -> JSONResponse:
    """GET /api/library — return all books."""
    return JSONResponse(load_library())


async def api_library_post(request: Request) -> JSONResponse:
    """POST /api/library — add a book (body: book JSON)."""
    try:
        book = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    books = load_library()
    if any(b.get("id") == book.get("id") for b in books):
        return JSONResponse({"error": "Book already exists."}, status_code=409)

    book.setdefault("dateAdded", today())
    books.append(book)
    save_library(books)
    return JSONResponse(book, status_code=201)


async def api_library_patch(request: Request) -> JSONResponse:
    """PATCH /api/library/{id} — update fields on a book."""
    book_id = int(request.path_params["id"])
    try:
        updates = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    books = load_library()
    for book in books:
        if book.get("id") == book_id:
            book.update(updates)
            save_library(books)
            return JSONResponse(book)

    return JSONResponse({"error": "Book not found."}, status_code=404)


async def api_library_delete(request: Request) -> Response:
    """DELETE /api/library/{id} — remove a book."""
    book_id = int(request.path_params["id"])
    books = load_library()
    new_books = [b for b in books if b.get("id") != book_id]
    if len(new_books) == len(books):
        return JSONResponse({"error": "Book not found."}, status_code=404)
    save_library(new_books)
    return Response(status_code=204)


async def api_library_import(request: Request) -> JSONResponse:
    """POST /api/library/import — import books from exported JSON."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    incoming = payload if isinstance(payload, list) else payload.get("books", [])
    if not isinstance(incoming, list):
        return JSONResponse({"error": "Expected a list of books."}, status_code=400)

    books = load_library()
    existing_ids = {b.get("id") for b in books}
    added = 0
    for book in incoming:
        if book.get("id") not in existing_ids:
            books.append(book)
            existing_ids.add(book.get("id"))
            added += 1

    save_library(books)
    return JSONResponse({"imported": added, "skipped": len(incoming) - added})


# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────

routes = [
    Route("/", index),
    Route("/api/analyse", api_analyse, methods=["POST"]),
    Route("/api/library", api_library_get, methods=["GET"]),
    Route("/api/library", api_library_post, methods=["POST"]),
    Route("/api/library/import", api_library_import, methods=["POST"]),
    Route("/api/library/{id:int}", api_library_patch, methods=["PATCH"]),
    Route("/api/library/{id:int}", api_library_delete, methods=["DELETE"]),
    Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
