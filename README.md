# Comprehensible Reading

A local reading tracker and readability analyser for Spanish and English books.
Analyse `.epub` and `.pdf` files to get readability scores, track your reading
library, and visualise reading statistics — all running on your own machine.
Nothing leaves your device.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager

## Quick start

```bash
uv run main.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.
`uv` handles the virtual environment and all dependencies automatically on first run.

## Project layout

```
comprehensible-reading/
├── main.py               # HTTP server and API routes (Starlette)
├── extraction.py         # Text extraction from .epub and .pdf files
├── language.py           # Language detection (ES, EN, PT, FR, DE)
├── readability.py        # Readability scoring pipeline
├── library.py            # Persistence for books and tags (JSON files)
├── bookmory_import.py    # Import from Bookmory (.bookmory files)
├── pyproject.toml        # Project metadata and dependencies
├── library.json          # Your book library (auto-created)
├── tags.json             # Your tag definitions (auto-created)
└── templates/
    └── index.html        # Single-page frontend (HTML + CSS + JS)
```

## Features

### Analyze tab
Upload an `.epub` or `.pdf` file to get:
- **Language detection** — Spanish and English are fully supported with dedicated
  formulas; other languages are detected but scores can be overridden manually
- **Text statistics** — word count, sentence count, average sentence length,
  syllables per word, polysyllabic word percentage
- **Readability formulas** — three formulas for Spanish, three for English (see below)
- **Author and title** — read automatically from the file's metadata
- **Add to library** — saves the book with its scores; detects duplicates by title
  and offers to update scores on the existing entry instead

### Library tab
- Books grouped by status: Currently Reading → Paused → Planned → Finished
- Summary bar: total books, finished, reading, planned, paused, total words
- Search by title, author
- **Edit panel** (click Edit on any book): author, language, words, difficulty,
  status, start date, finish date
- **Tags** — assign colour-coded tags to books; add/remove per book inline
- Import/export as JSON; import from Bookmory (`.bookmory` files)

### Statistics tab
- Filter by period: All time / This year / Last year
- Summary: total finished books, total words read, breakdown per language
- Per-language section:
  - **By difficulty** — horizontal stacked bar (words proportional to width),
    coloured from green (easy) to red (difficult)
  - **By tag** — vertical bars per tag, sorted by colour then length, each bar's
    width proportional to words read

### Tags tab
- Create tags with a name and colour
- Toggle "Show in stats" to include a tag in the Statistics breakdown
- Edit tag name/colour (Enter to save, Esc to cancel)
- Remove — shows which books use the tag before deleting

## Readability formulas

### Spanish
| Formula | What it measures |
|---|---|
| Flesch Reading Ease (adapted) | 0–100; higher = easier |
| Szigriszt–Pazos (Perspicuidad) | Gold standard for Spanish; higher = easier |
| Crawford Formula | School grade level (1–9+) |

### English
| Formula | What it measures |
|---|---|
| Flesch Reading Ease | 0–100; higher = easier |
| Flesch–Kincaid Grade Level | US school grade level (1–16+) |
| Gunning Fog Index | Years of education needed to read comfortably |

### Difficulty scale
All formulas are mapped to a unified 1–5 scale used across the library and
statistics views:

| Value | Label |
|---|---|
| 1 | Very easy |
| 2 | Easy |
| 3 | Medium |
| 4 | Difficult |
| 5 | Very difficult |

You can override the computed difficulty manually per book in the Edit panel.

## Importing from Bookmory

The Import button in the Library tab accepts `.bookmory` files directly.
The importer reads the embedded SQLite database, maps reading statuses,
extracts dates, and detects the language from title and description text.
Word count and difficulty are left blank for you to fill in.
Books already in your library (matched by title) are skipped.

## Data files

| File | Contents |
|---|---|
| `library.json` | All book records — title, author, language, scores, status, dates, tags, words |
| `tags.json` | Tag definitions — name, colour, showInStats flag |

Both files are plain JSON. Back them up, version-control them, or inspect them
directly. The Export button in the Library tab downloads a timestamped copy.

## Production deployment

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Suitable for Railway, Render, Fly.io, or any host that runs Python.
Note: `library.json` and `tags.json` are written to the same directory as
`main.py`, so persistent storage is required if deploying to a ephemeral host.
