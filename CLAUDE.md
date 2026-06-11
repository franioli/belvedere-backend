# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Response style

Keep all answers short and accurate. No verbose explanations, no padding. Go straight to the point. When showing code, show only the relevant diff or snippet. Do not include the full file unless explicitly asked. Always use markdown formatting for code.

## Session start

On a fresh session, read the `context/` files before editing anything:
- `context/architecture.md` — apps, models, API endpoints, shared modules, infrastructure
- `context/django-migration-status.md` — DB state, migration history, what stays outside Django

Inspect current source files before proposing architecture changes.

## Commands

```bash
uv sync                                          # install deps
uv run python manage.py runserver                # dev server
uv run python manage.py migrate
uv run python manage.py makemigrations
uv run python manage.py test                     # all tests
uv run python manage.py test surveys.tests.TestClass.test_method  # single test
uv run ruff check . && uv run ruff format .      # lint + format
uv run python manage.py index_s3_images [--camera-id ID] [--dry-run] [--force] [--workers N]
uv run python manage.py index_s3_products [--bucket B] [--dry-run]
uv run python manage.py collectstatic --noinput  # production
```

## Hard rules

- **Database is fully Django-managed** (single `public` schema). Every schema change — tables **and Postgres views** — goes through a migration. Never apply manual DDL (pgAdmin/QGIS) to project relations.
- The live DB is shared with QGIS users; guard data-touching migrations and take a `pg_dump` before destructive DDL.
- Two apps (`surveys`, `image_index`), one PostgreSQL/PostGIS database. Never split into separate databases.
- Reuse the shared S3/metadata helpers (`image_index/s3_utils.py`, `image_index/image_metadata.py`) — single source of truth, do not duplicate logic.
- External viewers consume the HTTP API (`/surveys/`, `/cams/`); keep API response shapes backward-compatible.

## Coding standards

- **Always** use type annotations.
- **Docstrings:** Google style, only when non-trivial. One-line max for simple functions.
- **Comments:** only for non-obvious logic.
- Single-purpose functions. No over-engineering. No premature abstractions.
- By default assume tests should be written for new code; ask if unclear.
