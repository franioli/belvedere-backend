from pathlib import PurePosixPath

import boto3
from botocore.client import Config
from django.conf import settings
from django.core.management.base import BaseCommand

from image_index.models import Camera, Image

s3 = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    region_name=settings.S3_REGION_NAME,
    config=Config(
        signature_version="s3v4",
        s3={
            "addressing_style": "virtual",
            "payload_signing_enabled": False,
        },
    ),
)


class Command(BaseCommand):
    help = "Index images from S3 for all active cameras"

    def add_arguments(self, parser):
        parser.add_argument("--camera-id", type=int, help="Index only one camera")
        parser.add_argument("--bucket", type=str, help="Override bucket")
        parser.add_argument("--prefix", type=str, help="Override prefix")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        s3 = boto3.client("s3")

        qs = Camera.objects.filter(is_active=True)
        if options["camera_id"]:
            qs = qs.filter(id=options["camera_id"])

        total_created = 0
        total_updated = 0
        total_seen = 0

        for camera in qs:
            bucket = options["bucket"] or camera.s3_bucket
            prefix = options["prefix"] or camera.s3_prefix

            self.stdout.write(
                f"Indexing camera={camera.id} {camera.camera_name} bucket={bucket} prefix={prefix}"
            )

            paginator = s3.get_paginator("list_objects_v2")
            page_iter = paginator.paginate(Bucket=bucket, Prefix=prefix)

            seen_for_camera = 0
            for page in page_iter:
                for obj in page.get("Contents", []):
                    key = obj["Key"]

                    if key.endswith("/"):
                        continue

                    lower = key.lower()
                    if not lower.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff")):
                        continue

                    total_seen += 1
                    seen_for_camera += 1

                    defaults = {
                        "camera": camera,
                        "filename": PurePosixPath(key).name,
                        "file_size_bytes": obj.get("Size"),
                        "s3_etag": (obj.get("ETag") or "").strip('"') or None,
                        "s3_last_modified": obj.get("LastModified"),
                        "bucket": bucket,
                        "is_indexed": True,
                    }

                    if not options["dry_run"]:
                        image, created = Image.objects.update_or_create(
                            bucket=bucket,
                            object_key=key,
                            defaults=defaults,
                        )
                        if created:
                            total_created += 1
                        else:
                            total_updated += 1

                    if options["limit"] and seen_for_camera >= options["limit"]:
                        break

                if options["limit"] and seen_for_camera >= options["limit"]:
                    break

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. seen={total_seen}, created={total_created}, updated={total_updated}"
            )
        )
