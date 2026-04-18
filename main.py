"""
main.py — Comprehensible Reading local web server.

Run with:
    uv run main.py

Or in production:
    uvicorn main:app --host 0.0.0.0 --port 8000
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

import extraction
import readability
import library as lib_store
import bookmory_import

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

jinja = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


# ─────────────────────────────────────────────────────────────
# Routes — pages
# ─────────────────────────────────────────────────────────────

async def index(request: Request) -> HTMLResponse:
    template = jinja.get_template("index.html")
    return HTMLResponse(template.render())


# ─────────────────────────────────────────────────────────────
# Routes — analysis
# ─────────────────────────────────────────────────────────────

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

        data = await upload.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        try:
            result = readability.analyse(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        return JSONResponse({
            "title": result.title,
            "author": result.author,
            "stats": asdict(result.stats),
            "scores": asdict(result.scores),
            "language": asdict(result.language),
        })

    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"Processing error: {exc}"}, status_code=500)


# ─────────────────────────────────────────────────────────────
# Routes — library
# ─────────────────────────────────────────────────────────────

async def api_import_bookmory(request: Request) -> JSONResponse:
    """POST /api/import/bookmory — import a .bookmory file (multipart upload)."""
    try:
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            return JSONResponse({"error": "No file provided."}, status_code=400)
        data = await upload.read()
        with tempfile.NamedTemporaryFile(suffix=".bookmory", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            imported_books = bookmory_import.convert(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        books = lib_store.load()
        existing_titles = {b.get("title", "").lower() for b in books}
        added = 0
        skipped = 0
        for book in imported_books:
            if book["title"].lower() in existing_titles:
                skipped += 1
            else:
                book.setdefault("tags", [])
                books.append(book)
                existing_titles.add(book["title"].lower())
                added += 1
        lib_store.save(books)
        return JSONResponse({"imported": added, "skipped": skipped})
    except Exception as exc:
        return JSONResponse({"error": f"Import error: {exc}"}, status_code=500)


async def api_library_get(request: Request) -> JSONResponse:
    return JSONResponse(lib_store.load())


async def api_library_post(request: Request) -> JSONResponse:
    try:
        book = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    # force=true bypasses the duplicate-title check (used by "Add as new entry")
    force = str(book.pop("force", "")).lower() in ("true", "1", "yes")

    books = lib_store.load()

    # Check by id — always enforced
    if any(b.get("id") == book.get("id") for b in books):
        # Assign a fresh id so the caller doesn't have to
        book["id"] = int(date.today().strftime("%Y%m%d%H%M%S%f"))

    if not force:
        # Check by title (case-insensitive)
        title_lower = (book.get("title") or "").strip().lower()
        if title_lower:
            existing = next(
                (b for b in books if (b.get("title") or "").strip().lower() == title_lower),
                None,
            )
            if existing:
                return JSONResponse(
                    {"error": "duplicate_title", "existing": existing},
                    status_code=409,
                )

    book.setdefault("dateAdded", date.today().isoformat())
    book.setdefault("tags", [])
    books.append(book)
    lib_store.save(books)
    return JSONResponse(book, status_code=201)


async def api_library_patch(request: Request) -> JSONResponse:
    book_id = int(request.path_params["id"])
    try:
        updates = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    books = lib_store.load()
    for book in books:
        if book.get("id") == book_id:
            book.update(updates)
            lib_store.save(books)
            return JSONResponse(book)

    return JSONResponse({"error": "Book not found."}, status_code=404)


async def api_library_delete(request: Request) -> Response:
    book_id = int(request.path_params["id"])
    books = lib_store.load()
    new_books = [b for b in books if b.get("id") != book_id]
    if len(new_books) == len(books):
        return JSONResponse({"error": "Book not found."}, status_code=404)
    lib_store.save(new_books)
    return Response(status_code=204)


async def api_library_import(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    incoming = payload if isinstance(payload, list) else payload.get("books", [])
    if not isinstance(incoming, list):
        return JSONResponse({"error": "Expected a list of books."}, status_code=400)

    books = lib_store.load()
    existing_ids = {b.get("id") for b in books}
    added = 0
    for book in incoming:
        if book.get("id") not in existing_ids:
            book.setdefault("tags", [])
            books.append(book)
            existing_ids.add(book.get("id"))
            added += 1

    lib_store.save(books)
    return JSONResponse({"imported": added, "skipped": len(incoming) - added})


# ─────────────────────────────────────────────────────────────
# Routes — tags
# ─────────────────────────────────────────────────────────────

async def api_tags_get(request: Request) -> JSONResponse:
    """GET /api/tags — all tag definitions."""
    return JSONResponse(lib_store.load_tags())


async def api_tags_post(request: Request) -> JSONResponse:
    """POST /api/tags — create a tag."""
    try:
        tag = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    tags = lib_store.load_tags()
    if any(t["name"] == tag.get("name") for t in tags):
        return JSONResponse({"error": "Tag already exists."}, status_code=409)

    new_tag = {
        "name": tag["name"],
        "color": tag.get("color", "#6b6560"),
        "showInStats": tag.get("showInStats", False),
    }
    tags.append(new_tag)
    lib_store.save_tags(tags)
    return JSONResponse(new_tag, status_code=201)


async def api_tags_patch(request: Request) -> JSONResponse:
    """PATCH /api/tags/{name} — update a tag."""
    tag_name = request.path_params["name"]
    try:
        updates = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    tags = lib_store.load_tags()
    for tag in tags:
        if tag["name"] == tag_name:
            tag.update(updates)
            lib_store.save_tags(tags)
            return JSONResponse(tag)

    return JSONResponse({"error": "Tag not found."}, status_code=404)


async def api_tags_delete(request: Request) -> Response:
    """DELETE /api/tags/{name} — remove a tag and detach from books."""
    tag_name = request.path_params["name"]
    tags = lib_store.load_tags()
    new_tags = [t for t in tags if t["name"] != tag_name]
    if len(new_tags) == len(tags):
        return JSONResponse({"error": "Tag not found."}, status_code=404)
    lib_store.save_tags(new_tags)

    # Remove tag from all books
    books = lib_store.load()
    for book in books:
        book["tags"] = [t for t in book.get("tags", []) if t != tag_name]
    lib_store.save(books)

    return Response(status_code=204)


async def api_library_update_scores(request: Request) -> JSONResponse:
    """PATCH /api/library/{id}/scores — update only scores+lang of an existing book."""
    book_id = int(request.path_params["id"])
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    books = lib_store.load()
    for book in books:
        if book.get("id") == book_id:
            book["scores"]    = payload.get("scores", book.get("scores", {}))
            book["lang"]      = payload.get("lang", book.get("lang"))
            book["lang_name"] = payload.get("lang_name", book.get("lang_name"))
            book["words"]     = payload.get("words", book.get("words", 0))
            lib_store.save(books)
            return JSONResponse(book)

    return JSONResponse({"error": "Book not found."}, status_code=404)


# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────

routes = [
    Route("/", index),
    Route("/api/analyse", api_analyse, methods=["POST"]),
    Route("/api/import/bookmory", api_import_bookmory, methods=["POST"]),
    Route("/api/library", api_library_get, methods=["GET"]),
    Route("/api/library", api_library_post, methods=["POST"]),
    Route("/api/library/import", api_library_import, methods=["POST"]),
    Route("/api/library/{id:int}", api_library_patch, methods=["PATCH"]),
    Route("/api/library/{id:int}", api_library_delete, methods=["DELETE"]),
    Route("/api/library/{id:int}/scores", api_library_update_scores, methods=["PATCH"]),
    Route("/api/tags", api_tags_get, methods=["GET"]),
    Route("/api/tags", api_tags_post, methods=["POST"]),
    Route("/api/tags/{name:str}", api_tags_patch, methods=["PATCH"]),
    Route("/api/tags/{name:str}", api_tags_delete, methods=["DELETE"]),
    Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
