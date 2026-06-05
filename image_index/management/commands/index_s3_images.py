from pathlib import PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from image_index.image_metadata import (
    IMAGE_EXTENSIONS,
    extract_image_metadata_from_bytes,
    parse_datetime_from_filename,
)
from image_index.models import Camera, Image
from image_index.s3_utils import build_s3_client, get_object_bytes

BATCH_SIZE = 500


def extract_image_metadata(s3, bucket, key, filename):
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


class Command(BaseCommand):
    help = "Index images from S3 buckets into the Image table"

    def add_arguments(self, parser):
        parser.add_argument("--camera-id", type=int, help="Index only one camera by ID")
        parser.add_argument("--bucket", type=str, help="Override bucket name")
        parser.add_argument(
            "--prefix", type=str, help="Override prefix for selected camera"
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)

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

        total_seen = 0
        total_matched = 0
        total_upserted = 0
        batch_size = options["batch_size"]

        for camera in qs:
            bucket = options["bucket"] or camera.s3_bucket
            prefix = (
                options["prefix"] if options["prefix"] is not None else camera.s3_prefix
            )

            if prefix and not prefix.endswith("/"):
                prefix = f"{prefix}/"

            self.stdout.write(
                f"Indexing camera={camera.id} name={camera.camera_name} bucket={bucket} prefix={prefix or ''}"
            )

            paginator = s3.get_paginator("list_objects_v2")
            page_iter = paginator.paginate(
                Bucket=bucket,
                Prefix=prefix or "",
                PaginationConfig={"PageSize": 1000},
            )

            batch = []
            matched_for_camera = 0
            seen_for_camera = 0
            upserted_for_camera = 0

            def flush_batch():
                nonlocal batch, total_upserted, upserted_for_camera
                if not batch or options["dry_run"]:
                    batch = []
                    return

                Image.objects.bulk_create(
                    batch,
                    batch_size=batch_size,
                    update_conflicts=True,
                    update_fields=[
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
                    ],
                    unique_fields=["bucket", "object_key"],
                )
                total_upserted += len(batch)
                upserted_for_camera += len(batch)
                batch = []

            for page in page_iter:
                for obj in page.get("Contents", []):
                    total_seen += 1
                    seen_for_camera += 1

                    key = obj["Key"]
                    if key.endswith("/"):
                        continue
                    if not key.lower().endswith(IMAGE_EXTENSIONS):
                        continue

                    matched_for_camera += 1
                    total_matched += 1

                    etag = (obj.get("ETag") or "").strip('"') or None
                    size = obj.get("Size")
                    last_modified = obj.get("LastModified")
                    filename = PurePosixPath(key).name

                    metadata = extract_image_metadata(s3, bucket, key, filename)

                    if options["dry_run"]:
                        self.stdout.write(
                            f"  DRY RUN {key} | dt={metadata['datetime']} | size={metadata['width_px']}x{metadata['height_px']}"
                        )
                    else:
                        batch.append(
                            Image(
                                camera=camera,
                                bucket=bucket,
                                object_key=key,
                                filename=filename,
                                file_size_bytes=size,
                                s3_etag=etag,
                                s3_last_modified=last_modified,
                                datetime=metadata["datetime"],
                                width_px=metadata["width_px"],
                                height_px=metadata["height_px"],
                                mime_type=metadata["mime_type"],
                                exif_data=metadata["exif_data"],
                                rotation=metadata["rotation"],
                                is_indexed=True,
                            )
                        )
                        if len(batch) >= batch_size:
                            flush_batch()

                    if options["limit"] and matched_for_camera >= options["limit"]:
                        break

                if options["limit"] and matched_for_camera >= options["limit"]:
                    break

            flush_batch()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Camera {camera.id}: seen={seen_for_camera}, matched={matched_for_camera}, upserted={upserted_for_camera}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. seen={total_seen}, matched={total_matched}, upserted={total_upserted}"
            )
        )
