# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Spendly — a Flask expense tracker built incrementally as a guided, step-based project. Routes and modules that aren't built yet are left as explicit stub placeholders (e.g. `database/db.py` and several routes in `app.py` are marked "students will implement this in Step N"). When asked to build one of these, implement only what's asked — don't jump ahead and build later steps.

## Commands

```bash
# activate the existing virtualenv (already created under env/)
source env/bin/activate

# install dependencies
pip install -r requirements.txt

# run the dev server (http://localhost:5001, debug mode on)
python app.py

# run tests (pytest-flask is a dependency, but no tests exist yet)
pytest
```

There is no lint/format tooling configured in this repo.

## Architecture

- **`app.py`** — single-file Flask app. All routes are defined directly on the module-level `app` object (no blueprints). Each route renders a template with `render_template`; there is no application factory.
- **`database/db.py`** — intended to hold `get_db()` (SQLite connection with `row_factory` and foreign keys on), `init_db()` (`CREATE TABLE IF NOT EXISTS` statements), and `seed_db()` (sample data for dev). Not yet implemented — this is where persistence will live once expense/user features are built. The SQLite file itself (`expense_tracker.db`) is gitignored and created locally.
- **Templates (`templates/`)** — Jinja2, all extend `base.html`, which defines the shared navbar/footer chrome and three blocks: `title`, `head` (for page-specific `<link>` tags), and `scripts` (for page-specific `<script>` tags). `content` is not a named override point in `base.html`'s outer structure — page templates place their body inside `{% block content %}`.
- **Static assets (`static/`)** — `css/style.css` holds shared/base styles used across all pages; page-specific styles live in their own file (e.g. `css/landing.css` for the landing page) and are pulled in via that page's `head` block. `js/main.js` is loaded globally on every page via `base.html`; page-specific interactive behavior (e.g. the landing page's video modal) is instead written inline inside that page's `scripts` block rather than added to `main.js`.
- **Auth/data routes are placeholders.** `/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` currently return plain placeholder strings, not templates — they're wired up in later steps once the database layer exists. `/register` and `/login` currently only render forms (GET); there is no POST handler or session/auth logic yet, so the forms don't submit anywhere functional.

## Notes

- `.gitignore` includes `*.md`, so this file (and any other Markdown) is excluded from git by default — if this file should be tracked, adjust `.gitignore` accordingly.
