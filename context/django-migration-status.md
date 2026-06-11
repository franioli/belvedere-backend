# Django Migration Status

## Goal (ACHIEVED — June 2026)

The project/database is now in a fully Django-managed state:
- models are the authoritative schema definition
- all tables live in a single `public` schema
- schema changes (tables **and views**) happen through Django migrations
- the full migration chain builds a complete database from scratch (validated by the test suite)

## What was done (migrations `surveys/0008`–`0014`, applied June 2026)

### 0008 — un-shadow `points` / `surveys`
The legacy views `public.points` (aggregate) and `public.surveys` shadowed the
real `core.points`/`core.surveys` tables via the `public,core` search_path, so
Django models read views instead of tables — and `Point` admin saves failed
(aggregate views are not updatable). Fixed by renaming `public.points` →
`points_summary`, dropping `public.surveys`, and removing the three
view-computed fields (`first_survey_date`, `last_survey_date`,
`num_measurements`) from the `Point` model. `PointAdmin` now computes them
with queryset annotations.

### 0009 — single schema
All 12 `core` tables moved to `public` (`ALTER TABLE ... SET SCHEMA`), the
`compute_measurement_geometry()` trigger function moved with them, the empty
`core` schema dropped. `settings.py` search_path is now just `public`.

### 0010 — products & volumes modelled
Legacy pandas/shapefile tables `2d_products`, `3d_products`, `volumes`
replaced by clean Django models `Product2D` (`products_2d`), `Product3D`
(`products_3d`), `Volume` (`volumes`); data copied, truncated column names
expanded, all-NULL `average_no` dropped. Products carry S3 reference fields
(`bucket`, `object_key`, etag/size/last-modified, `is_uploaded`) mirroring
`image_index.Image`; `S3_PRODUCTS_BUCKET_NAME` setting (default
`belvedere-products`, bucket not yet created) and the `index_s3_products`
management command provide the upload-indexing infrastructure.

### 0011 — views under migration control
Surviving views adopted into migrations (DDL now version-controlled, created
on fresh DBs): `points_measurements`, `points_movement_raw`,
`points_movement_filtered`, `active_points`. Dropped as legacy:
`points_summary` (0011), plus manually by the user: `measurements_2015..2023`
per-year views, `scatter_points_measurements`, `scatter_points_movement`.

**Rule going forward:** any change to these views must be a new migration
(`CREATE OR REPLACE VIEW` + reverse), never manual DDL in pgAdmin.

### 0012–0014 — admin polish & views in admin
Meta/verbose-name tweaks (state-only) and unmanaged models
(`managed = False`) over the four kept views: `PointsMeasurement`,
`PointsMovementRaw`, `PointsMovementFiltered`, `ActivePoint` — exposed in the
Django admin as browse-only pages (`ReadOnlyViewAdmin`).

## Surveys API (June 2026)

REST endpoints under `/surveys/` now serve the data the legacy PHP viewers
used to read straight from the views (`surveys/urls.py`, `views.py`,
`serializers.py`):

- `GET /surveys/years/` — distinct survey years with measurements
- `GET /surveys/measurements/?year=YYYY&is_fixed=false` — plain JSON array,
  field names identical to the `points_measurements` view
- `GET /surveys/points/<label>/velocity/` — yearly velocity series computed in
  Python (`surveys/utils/velocity.py`), verified identical to
  `points_movement_filtered` over all 93 labels / 171 records

The DB views therefore remain only for QGIS; external consumers should use
the API.

## Intentionally outside Django

- `scatter_points`, `scatter_measurements` — legacy tables kept for reference
  only (see comment block at the bottom of `surveys/models.py`)
- `layer_styles`, `qgis_projects` — owned by QGIS
- `spatial_ref_sys` — PostGIS
- `raster.geoid_model` — geoid raster sampled by the
  `compute_measurement_geometry` BEFORE INSERT/UPDATE trigger on
  `measurements` (computes `geom`, `lat`, `lon`, `h_orto`)
