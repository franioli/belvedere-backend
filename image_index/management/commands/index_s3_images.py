from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max

from image_index.image_metadata import (
    IMAGE_EXTENSIONS,
    extract_image_metadata_from_bytes,
    parse_datetime_from_filename,
)
from image_index.models import Camera, Image
from image_index.s3_utils import build_s3_client, get_object_bytes

INCREMENTAL_BUFFER_DAYS = 7

BATCH_SIZE = 200
DEFAULT_WORKERS = 2  # Keep low to run on vps


def _fetch_and_extract(s3, bucket, key, filename):
    """Fetch image bytes from S3 and extract metadata. Designed to run in a thread."""
    try:
        image_bytes, mime_type = get_object_bytes(s3, bucket, key)
        return extract_image_metadata_from_bytes(
            image_bytes,
            filename=filename,
            mime_type=mime_type,
        )
    except Exception:
        return {
            "datetime": parse_datetime_from_filename(filename),
            "width_px": None,
            "height_px": None,
            "mime_type": None,
            "exif_data": None,
            "rotation": 0,
        }


_UPDATE_FIELDS = [
    "camera",
    "filename",
    "file_size_bytes",
    "s3_etag",
    "s3_last_modified",
    "datetime",
    "width_px",
    "height_px",
    "mime_type",
    "exif_data",
    "rotation",
    "is_indexed",
    "updated_at",
]


class Command(BaseCommand):
    help = "Index images from S3 buckets into the Image table"

    def _flush_batch(
        self,
        batch: list,
        batch_size: int,
        counts: dict,
        grand_total: dict,
        dry_run: bool,
    ) -> None:
        if not batch or dry_run:
            batch.clear()
            return

        n = len(batch)
        Image.objects.bulk_create(
            batch,
            batch_size=batch_size,
            update_conflicts=True,
            update_fields=_UPDATE_FIELDS,
            unique_fields=["bucket", "object_key"],
        )
        counts["upserted"] += n
        grand_total["upserted"] += n
        self.stdout.write(
            f"  flushed {n} rows | "
            f"seen={counts['seen']} matched={counts['matched']} "
            f"skipped={counts['skipped']} upserted={counts['upserted']}"
        )
        batch.clear()

    def add_arguments(self, parser):
        parser.add_argument("--camera-id", type=int, help="Index only one camera by ID")
        parser.add_argument("--bucket", type=str, help="Override bucket name")
        parser.add_argument(
            "--prefix", type=str, help="Override prefix for selected camera"
        )
        parser.add_argument(
            "--incremental",
            action="store_true",
            help=(
                "Skip objects older than the watermark (max s3_last_modified in DB minus --incremental-buffer-days). Faster for routine runs when most objects are already indexed."
            ),
        )
        parser.add_argument(
            "--incremental-buffer-days",
            type=int,
            default=INCREMENTAL_BUFFER_DAYS,
            help=(
                "How many days before the watermark to still re-check (default: 7). Covers re-uploads and clock skew."
            ),
        )
        parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
        parser.add_argument(
            "--workers",
            type=int,
            default=DEFAULT_WORKERS,
            help="Number of parallel threads for S3 fetch + EXIF extraction (default: 8)",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-fetch and re-index even unchanged objects (ETag match)",
        )
        parser.add_argument(
            "--limit", type=int, help="Limit number of objects to process (for testing)"
        )

    def handle(self, *args, **options):
        if not settings.S3_ENDPOINT_URL:
            raise CommandError("S3_ENDPOINT_URL is not configured")
        if not settings.S3_ACCESS_KEY or not settings.S3_SECRET_KEY:
            raise CommandError("S3 credentials are not configured")

        s3 = build_s3_client()

        qs = Camera.objects.all().order_by("id")
        if options["camera_id"]:
            qs = qs.filter(id=options["camera_id"])

        if not qs.exists():
            raise CommandError("No cameras found for the selected filters")

        batch_size = options["batch_size"]
        workers = max(1, options["workers"])

        grand_total = {"seen": 0, "matched": 0, "skipped": 0, "upserted": 0}

        for camera in qs:
            bucket = options["bucket"] or camera.s3_bucket
            prefix = (
                options["prefix"] if options["prefix"] is not None else camera.s3_prefix
            )

            if prefix and not prefix.endswith("/"):
                prefix = f"{prefix}/"

            self.stdout.write(
                f"\nIndexing camera={camera.id} name={camera.camera_name} "
                f"bucket={bucket} prefix={prefix or ''} workers={workers}"
            )

            # --- Incremental watermark ---
            watermark = None
            buffer_start = None
            if options["incremental"] and not options["force"]:
                watermark = Image.objects.filter(
                    camera=camera, bucket=bucket
                ).aggregate(Max("s3_last_modified"))["s3_last_modified__max"]
                if watermark is not None:
                    buffer_start = watermark - timedelta(
                        days=options["incremental_buffer_days"]
                    )
                    self.stdout.write(
                        f"  incremental mode: watermark={watermark.isoformat()} "
                        f"buffer_start={buffer_start.isoformat()}"
                    )
                else:
                    self.stdout.write("  incremental mode: no watermark yet, full scan")

            # --- Phase 1: load existing ETags from DB to enable skip logic ---
            etag_qs = Image.objects.filter(camera=camera, bucket=bucket)
            if buffer_start is not None:
                etag_qs = etag_qs.filter(s3_last_modified__gte=buffer_start)
            existing_etags: dict[str, str | None] = dict(
                etag_qs.values_list("object_key", "s3_etag")
            )
            self.stdout.write(f"  {len(existing_etags)} rows loaded from DB")

            paginator = s3.get_paginator("list_objects_v2")
            page_iter = paginator.paginate(
                Bucket=bucket,
                Prefix=prefix or "",
                PaginationConfig={"PageSize": 1000},
            )

            counts = {"seen": 0, "matched": 0, "skipped": 0, "upserted": 0}
            batch: list[Image] = []
            done = False

            # --- Phase 2: paginate + parallel fetch ---
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for page_num, page in enumerate(page_iter, start=1):
                    if done:
                        break

                    contents = page.get("Contents", [])
                    counts["seen"] += len(contents)
                    grand_total["seen"] += len(contents)

                    # Classify objects in this page: needs-fetch vs skip
                    to_fetch: list[tuple[str, str, str | None, int | None, object]] = []
                    for obj in contents:
                        key = obj["Key"]
                        if key.endswith("/") or not key.lower().endswith(
                            IMAGE_EXTENSIONS
                        ):
                            continue

                        counts["matched"] += 1
                        grand_total["matched"] += 1

                        etag = (obj.get("ETag") or "").strip('"') or None
                        size = obj.get("Size")
                        last_modified = obj.get("LastModified")
                        filename = PurePosixPath(key).name

                        # Incremental: skip objects older than the buffer window —
                        # they are guaranteed to be indexed already.
                        if (
                            buffer_start is not None
                            and last_modified is not None
                            and last_modified < buffer_start
                        ):
                            counts["skipped"] += 1
                            grand_total["skipped"] += 1
                            continue

                        # Skip if ETag matches an existing row (content unchanged)
                        if (
                            not options["force"]
                            and key in existing_etags
                            and existing_etags[key] == etag
                        ):
                            counts["skipped"] += 1
                            grand_total["skipped"] += 1
                            continue

                        to_fetch.append((key, filename, etag, size, last_modified))

                        if options["limit"] and counts["matched"] >= options["limit"]:
                            done = True
                            break

                    self.stdout.write(
                        f"  page {page_num}: {len(contents)} objects | "
                        f"to fetch={len(to_fetch)} | "
                        f"skipped so far={counts['skipped']}"
                    )

                    if not to_fetch:
                        continue

                    if options["dry_run"]:
                        for key, filename, _etag, _size, _last_modified in to_fetch:
                            meta = _fetch_and_extract(s3, bucket, key, filename)
                            self.stdout.write(
                                f"  DRY RUN {key} | "
                                f"dt={meta['datetime']} | "
                                f"size={meta['width_px']}x{meta['height_px']}"
                            )
                        continue

                    # Submit all fetches for this page in parallel
                    futures = {
                        pool.submit(_fetch_and_extract, s3, bucket, key, filename): (
                            key,
                            filename,
                            etag,
                            size,
                            last_modified,
                        )
                        for key, filename, etag, size, last_modified in to_fetch
                    }

                    for future in as_completed(futures):
                        key, filename, etag, size, last_modified = futures[future]
                        try:
                            meta = future.result()
                        except Exception as exc:
                            self.stderr.write(f"  ERROR {key}: {exc}")
                            continue

                        batch.append(
                            Image(
                                camera=camera,
                                bucket=bucket,
                                object_key=key,
                                filename=filename,
                                file_size_bytes=size,
                                s3_etag=etag,
                                s3_last_modified=last_modified,
                                datetime=meta["datetime"],
                                width_px=meta["width_px"],
                                height_px=meta["height_px"],
                                mime_type=meta["mime_type"],
                                exif_data=meta["exif_data"],
                                rotation=meta["rotation"],
                                is_indexed=True,
                            )
                        )
                        if len(batch) >= batch_size:
                            self._flush_batch(
                                batch,
                                batch_size,
                                counts,
                                grand_total,
                                options["dry_run"],
                            )

                    if done:
                        break

            self._flush_batch(
                batch, batch_size, counts, grand_total, options["dry_run"]
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Camera {camera.id} done: "
                    f"seen={counts['seen']} matched={counts['matched']} "
                    f"skipped={counts['skipped']} upserted={counts['upserted']}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nAll cameras done: "
                f"seen={grand_total['seen']} matched={grand_total['matched']} "
                f"skipped={grand_total['skipped']} upserted={grand_total['upserted']}"
            )
        )
