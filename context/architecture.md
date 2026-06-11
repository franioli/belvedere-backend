# Architecture

Backend for the **Belvedere Glacier monitoring project**: GNSS/photogrammetric
survey data and time-lapse camera imagery, served to external viewers
(potree 3D, web-map, camera-viewer in the `belvedere-viewers` repo) and to
QGIS (direct DB access).

One PostgreSQL/PostGIS database (`belvedere`), single `public` schema, fully
Django-managed (see `django-migration-status.md`). Never split into separate
databases.

## Apps

### `surveys` — survey domain
- `Survey`, `Instrument`, `SurveyHasInstrument`, `Flight` — campaign metadata
  (legacy integer PKs, explicit `db_table`)
- `Point`, `Measurement`, `MeasurementPhoto` — GNSS points and yearly
  measurements. A DB trigger (`compute_measurement_geometry`, BEFORE
  INSERT/UPDATE on `measurements`) computes `geom`, `lat`, `lon`, `h_orto`
  from `east`/`north`/`h` using the `raster.geoid_model` geoid raster.
- `Product2D` (`products_2d`), `Product3D` (`products_3d`), `Volume`
  (`volumes`) — survey data products with S3 reference fields
  (`bucket`, `object_key`, etag/size, `is_uploaded`); bucket
  `S3_PRODUCTS_BUCKET_NAME` (default `belvedere-products`, not yet created);
  synced by `manage.py index_s3_products [--bucket B] [--dry-run]`.
- Unmanaged read-only models over the Postgres views (`PointsMeasurement`,
  `PointsMovementRaw`, `PointsMovementFiltered`, `ActivePoint`) — browse-only
  admin pages; view DDL lives in migration `0011_adopt_views`.

API under `/surveys/` (plain JSON arrays, no pagination):
- `years/` — distinct survey years with measurements
- `measurements/?year=YYYY&is_fixed=true|false` — field names match the
  legacy `points_measurements` view
- `points/<label>/velocity/` — yearly velocity series, computed in
  `surveys/utils/velocity.py` (280 < dt < 400 days window, d > 0, v = d/dt)

### `image_index` — time-lapse camera catalogue
- `Camera`: S3 bucket/prefix, 3D PostGIS location, `is_active` controls indexing
- `CameraCalibration`: intrinsics/extrinsics as `ArrayField`; `CameraModel`
  IntEnum (includes custom `METASHAPE=11`)
- `Image`: one row per S3 object; `(bucket, object_key)` unique;
  `datetime`/`rotation` derived at save time from shared helpers

API under `/cams/`: `cameras/`, `images/` (DRF, paginated),
`images/<pk>/preview/`, `thumb/`, `preview-url/`, `thumb-url/`
(S3 proxy / presigned URLs). Reverse with
`reverse("image_index:serve_image_preview", args=[pk])`.

## Shared modules (single source of truth — do not duplicate)

- `image_index/s3_utils.py`: `build_s3_client()`, `build_readonly_s3_client()`,
  `get_object_bytes()`, `put_object_bytes()`, `generate_presigned_url()` —
  used by both apps
- `image_index/image_metadata.py`: `IMAGE_EXTENSIONS`, `FILENAME_DATETIME_RE`,
  `parse_datetime_from_filename()`, `parse_datetime_from_exif_dict()`,
  `make_json_safe()`, `extract_image_metadata_from_bytes()`

## Infrastructure

- Settings via `python-decouple` (`.env`); static files via `whitenoise`;
  CORS open; DRF anon throttle 300/min
- S3 (Hetzner object storage): `s3v4` signature + virtual addressing;
  `S3_ENDPOINT_URL` required for the indexing commands; buckets:
  `belvedere-images` (camera images), `belvedere-products` (survey products)
- External DB consumers: QGIS (`layer_styles`, `qgis_projects`, the views);
  viewers consume only the HTTP API
