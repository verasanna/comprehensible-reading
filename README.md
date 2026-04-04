# Comprehensible Reading

A Spanish reading level checker and personal reading tracker.
Analyzes `.epub` and `.pdf` files and computes three readability scores
calibrated for Spanish. Tracks your reading library locally with no
cloud dependencies.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager

## Quick start

```bash
# Clone or download the project, then:
uv run server.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

That's it. `uv` handles the virtual environment and all dependencies
automatically on first run.

## Project layout

```
comprehensible-reading/
├── pyproject.toml      # project metadata and dependencies
├── server.py           # local web server (Starlette)
├── reader.py           # epub/pdf text extraction and readability analysis
├── templates/
│   └── index.html      # single-page frontend
├── static/             # bundled JS libraries (no CDN at runtime)
│   ├── jszip.min.js
│   └── pdf.min.js / pdf.worker.min.js
└── README.md
```

## Readability formulas

| Formula | What it measures |
|---|---|
| Flesch Reading Ease (adapted) | 0–100 scale; higher = easier |
| Szigriszt–Pazos (Perspicuidad) | Gold standard for Spanish |
| Crawford Formula | School grade level for Spanish |

## Library data

Reading progress is stored in `library.json` in the project directory.
This file is plain JSON — easy to back up, version-control, or inspect.

## Deployment

For GitHub Pages: the project runs as a local server, not a static site.
To share it, deploy with any Python host (Railway, Render, Fly.io) using:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```
