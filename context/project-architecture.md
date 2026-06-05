# Project Architecture

## High-level structure
This backend is part of the Belvedere Glacier platform.

Broader project components mentioned in prior work:
- Django backend/app
- static/public site
- Potree pointcloud viewer
- webmap service
- GeoServer integration
- S3/object-storage-backed image ingestion

## Server / infrastructure context
- Migration to Hetzner Cloud was performed / is in progress.
- Services are consolidated under `/opt/services`.
- Services are managed by the `belvedere` user.
- PostgreSQL was containerized and a database dump was imported successfully.
- PostGIS is required / relevant for GIS and surveys workflows.
- Database exposure should be restricted; public access should happen only through app/API layers.

## Database architecture
Use one single PostgreSQL/PostGIS database for the Django project.

Apps:
- `image_index`
- `surveys`

Do not split them into separate databases unless explicitly requested.

Reasoning:
- simpler operations
- simpler migrations
- coherent Django ORM management
- easier constraints / joins / GIS integration

## Related infra notes
GeoServer work exists in the wider stack.
A separate GeoServer DB was considered useful for service isolation in some contexts, but the Django backend itself should keep a single coherent DB unless there is a strong operational reason to split later.

## Portability requirement
Public website, viewer, and public-facing content should stay portable and easy to move to another VPS in a future multi-VPS setup.