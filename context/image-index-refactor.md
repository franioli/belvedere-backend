# Image Index Refactor

## Goal
Remove duplicated logic across:
- `image_index/models.py`
- `image_index/management/commands/index_s3_images.py`
- `image_index/management/commands/update_image_datetimes.py`

## Shared modules

### image_index/s3_utils.py
Expected functions:
- `build_s3_client()`
- `get_object_bytes(s3, bucket, key)`

### image_index/image_metadata.py
Expected contents:
- `IMAGE_EXTENSIONS`
- `FILENAME_DATETIME_RE`
- `make_aware_if_needed(value)`
- `parse_datetime_from_filename(filename)`
- `parse_datetime_from_exif_dict(exif_data)`
- `make_json_safe(value)`  # recursive JSON-safe EXIF normalization
- `extract_exif_data_from_bytes(image_bytes)`
- `extract_image_metadata_from_bytes(image_bytes, filename=None, mime_type=None)`

## Current important bug
`update_image_datetimes` failed with:
`Object of type IFDRational is not JSON serializable`

Meaning:
- EXIF extraction is returning raw Pillow types
- these cannot be stored in Django `JSONField`
- sanitize in shared helper, not in the command

## JSON-safe conversion requirements
Recursively normalize:
- IFDRational -> float or string fallback
- bytes -> decoded string
- tuple/list/set -> JSON-safe lists
- dict -> recursively normalized values
- unknown object -> string fallback

## Image model rules
Model should reuse shared helpers:
- `parse_datetime_from_exif_dict`
- `parse_datetime_from_filename`

Model should not duplicate:
- regex
- date parsing logic
- EXIF candidate selection logic

`Image.file_path` should produce:
`https://<endpoint>/<bucket>/<encoded-object-key>`

## Commands

### index_s3_images.py
Behavior:
- iterate cameras
- list objects via paginator
- filter image extensions
- derive filename from object key
- fetch object bytes when metadata enrichment is needed
- upsert images in batches with `bulk_create(update_conflicts=True, ...)`

### update_image_datetimes.py
Behavior:
- simple loop, no batching needed
- optionally process only one image or one camera
- skip existing datetimes unless `--force`
- if no EXIF in DB, fetch object bytes from S3
- compute datetime
- store `datetime`
- optionally update `exif_data`
- save only changed fields

## Admin preview
Simplified final direction:
- remove `PreviewWidget`
- remove `ImageAdminForm` unless needed for another purpose
- use `image_preview`, `admin_thumbnail`, and `view_image` directly on `ImageAdmin`

## URL/view details
- `image_index/views.py` contains `serve_image(request, pk)`
- `image_index/urls.py` contains:
  - `app_name = "image_index"`
  - `path("images/<int:pk>/serve/", serve_image, name="serve_image")`
- reverse with:
  - `reverse("image_index:serve_image", args=[obj.pk])`