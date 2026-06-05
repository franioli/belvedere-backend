# Project Overview

This repository is the Django-based backend/application layer of the Belvedere Glacier project.

Main domain context:
- Belvedere Glacier platform / app
- S3-backed image ingestion from cameras
- surveys data and GIS-related workflows
- PostgreSQL/PostGIS as the single database backend
- Django admin used as the internal operational UI

This project is part of a broader Belvedere Glacier infrastructure that also includes:
- static/public website content
- Potree pointcloud viewer
- webmap services
- planned / deployed GeoServer integration
- S3/object-storage-backed image flows

Relevant repository/project context from prior work:
- Main project/repo context: https://github.com/franioli/thebelvedereglacier
- The app fetches images from S3-compatible storage where files are uploaded by cameras, typically through FTP workflows upstream.
- The broader infrastructure is being consolidated on a Hetzner Cloud server.
- Services are being organized under `/opt/services` and managed by the `belvedere` user.
- Database access should be private except through controlled application/API access.

# Workspace / App Structure

This Django codebase uses:
- one single PostgreSQL/PostGIS database
- two main Django apps:
  1. `image_index`
  2. `surveys`

Important architectural rule:
- keep a single database instance (Postgres/PostGIS) for the Django project
- do not split these apps into separate databases unless explicitly requested
- prefer one coherent Django-managed schema over hybrid unmanaged/manual drift

# Current Database Direction

The project is migrating from an existing/legacy database setup toward a fully Django-managed application schema.

This means:
- the database already exists and contains useful real data
- some or all tables may have originated outside Django or from a partially managed schema
- the target state is: schema, constraints, indexes, and future changes managed through Django migrations
- no silent schema drift between production DB and Django models

Use a careful migration strategy:
1. inspect current DB vs models
2. identify unmanaged / legacy tables
3. create or refine Django models for all needed tables
4. generate migrations intentionally
5. use fake/fake-initial only where justified and documented
6. preserve production data
7. remove duplicated logic and manual schema assumptions

# Coding Preferences

Apply these project preferences consistently:
- concise code
- avoid overengineering
- prefer simple, clear implementations
- moderate comments only
- Google-style docstrings when docstrings are useful
- test changes when practical
- do not introduce unnecessary abstractions
- keep answers and code explanations concise unless a deeper handoff is requested

# Current Refactor Focus

Main recent work has focused on `image_index`:
- S3 image indexing
- EXIF extraction
- datetime extraction
- Django admin image preview
- reducing duplicated logic across model + management commands

Shared helper modules now exist / should exist:
- `image_index/s3_utils.py`
- `image_index/image_metadata.py`

Desired responsibility split:
- `s3_utils.py`: S3 client + object byte retrieval
- `image_metadata.py`: filename parsing, EXIF parsing, metadata extraction, JSON-safe conversion
- `models.py`: model-specific persistence behavior only
- management commands: orchestration only

# Key Image Index Decisions

## Shared constants and helpers
The following should be defined once in `image_index/image_metadata.py` and imported elsewhere:
- `IMAGE_EXTENSIONS`
- `FILENAME_DATETIME_RE`
- `make_aware_if_needed(value)`
- `parse_datetime_from_filename(filename)`
- `parse_datetime_from_exif_dict(exif_data)`
- `extract_exif_data_from_bytes(image_bytes)`
- `extract_image_metadata_from_bytes(image_bytes, filename=None, mime_type=None)`

## Important EXIF rule
Pillow EXIF values may contain non-JSON-serializable types like `IFDRational`.
Those must be normalized recursively before storing to Django `JSONField`.

Required helper:
- `make_json_safe(value)` or equivalent recursive normalizer

It should convert:
- `IFDRational` -> float (or string fallback)
- `bytes` -> decoded string / string fallback
- tuples/lists/sets -> JSON-safe lists
- dicts -> recursively normalized dicts
- unknown objects -> string fallback

Fix belongs in shared helper code, not in each command.

## Datetime extraction priority
For each image:
1. EXIF datetime first
2. filename datetime fallback
3. else `None`

Preferred EXIF keys:
- `DateTimeOriginal`
- `EXIF DateTimeOriginal`
- `DateTimeDigitized`
- `EXIF DateTimeDigitized`
- `DateTime`
- `Image DateTime`

Filename pattern handled centrally via shared regex.

## Rotation handling
Rotation should be derived from EXIF orientation and support both:
- numeric EXIF orientation values: `1, 3, 6, 8`
- string variants such as:
  - `Horizontal (normal)`
  - `Rotated 90 CW`
  - `Rotated 180`
  - `Rotated 90 CCW`
  - `Rotated 270 CW`

# Image Model Expectations

`Image` should:
- derive `filename` from `object_key` if missing
- derive `datetime` via shared helpers if missing
- derive `rotation` from `exif_data`
- avoid duplicating regex/date parsing logic already in `image_metadata.py`

`Image.file_path` should return an HTTP object-storage URL, not `s3://...`

Expected format:
`{S3_ENDPOINT_URL}/{bucket}/{object_key}`

Implementation detail:
- use `urllib.parse.quote(object_key, safe="/")` to preserve `/` while encoding unsafe characters

Example:
`https://nbg1.your-objectstorage.com/belvedere-images/p1/p1_20211213_145628_IMG_0834.jpg`

# Management Commands

## 1. index_s3_images.py
Purpose:
- list S3 objects
- filter image keys by extension
- fetch image bytes
- extract metadata using shared helpers
- bulk upsert into `Image`

Status:
- refactored to use shared helper modules instead of duplicating parsing logic
- still verify helper reuse remains complete and no dead imports remain

## 2. update_image_datetimes.py
Purpose:
- simple update command for existing DB images
- no batch processing required
- optional filters: `--image-id`, `--camera-id`, `--force`, `--dry-run`, `--limit`
- if no EXIF stored, fetch bytes from S3 and extract EXIF
- compute datetime from EXIF first, filename fallback second
- save only changed fields via `update_fields`

Important known bug:
- failures occurred because EXIF contained `IFDRational`, not JSON-serializable
- fix must happen in shared metadata extraction

# Django Admin

The admin image preview now works through a dedicated view.

Simplification decision:
- no need for `PreviewWidget`
- no need for custom `ImageAdminForm` just for previews
- use `readonly_fields` and custom display methods instead

Preferred admin structure:
- `image_preview` in `readonly_fields`
- `admin_thumbnail` in `list_display`
- `view_image` as link

# Image Serve View

A dedicated Django view exists or should exist:
- `serve_image(request, pk)` in `image_index/views.py`

Purpose:
- fetch image bytes from S3
- return `HttpResponse` with correct content type

URLs:
- `image_index/urls.py`
- `app_name = "image_index"`
- route name: `serve_image`
- reverse with:
  `reverse("image_index:serve_image", args=[obj.pk])`

# Infrastructure Context

Broader infrastructure facts relevant to future decisions:
- Hetzner-hosted migration in progress / recently completed
- database imported into Dockerized PostgreSQL/PostGIS environment
- GeoServer work exists alongside this project
- public-facing site/viewer content should remain portable and separable for future multi-VPS setups
- database should be internet-accessible only for authorized users, public access only via app/API

# Claude Code Working Mode

When starting work:
1. read `CLAUDE.md`
2. read all files under `context/`
3. inspect current source files before changing architecture
4. preserve the single-DB Postgres/PostGIS design
5. prefer explicit checklists before risky schema changes
6. do not regenerate already-refactored duplication