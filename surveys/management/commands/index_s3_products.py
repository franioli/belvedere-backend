"""Index survey products (Product2D/Product3D) against the S3 products bucket.

For every product with an ``object_key`` set, looks up the object in the
bucket and updates its S3 metadata (etag, size, last modified, is_uploaded).
Bucket objects not referenced by any product are reported as orphans.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from image_index.s3_utils import build_s3_client
from surveys.models import BaseProduct, Product2D, Product3D


def list_bucket_objects(s3: Any, bucket: str) -> dict[str, dict[str, Any]]:
    """Return all objects in the bucket keyed by object key."""
    objects: dict[str, dict[str, Any]] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            objects[obj["Key"]] = obj
    return objects


class Command(BaseCommand):
    help = "Sync S3 metadata of survey products from the products bucket."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--bucket",
            default=settings.S3_PRODUCTS_BUCKET_NAME,
            help="S3 bucket to index (default: settings.S3_PRODUCTS_BUCKET_NAME).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be updated without writing to the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        bucket: str = options["bucket"]
        dry_run: bool = options["dry_run"]

        s3 = build_s3_client()
        objects = list_bucket_objects(s3, bucket)
        self.stdout.write(f"Found {len(objects)} objects in bucket '{bucket}'.")

        matched_keys: set[str] = set()
        for model in (Product2D, Product3D):
            updated = 0
            for product in model.objects.exclude(object_key__isnull=True).exclude(
                object_key=""
            ):
                obj = objects.get(product.object_key)
                if obj is None:
                    if product.is_uploaded:
                        self.stderr.write(
                            f"{model.__name__} {product.pk}: object "
                            f"'{product.object_key}' no longer in bucket."
                        )
                    continue
                matched_keys.add(product.object_key)
                self._sync_product(product, bucket, obj, dry_run)
                updated += 1
            self.stdout.write(f"{model.__name__}: {updated} product(s) synced.")

        orphans = sorted(set(objects) - matched_keys)
        if orphans:
            self.stdout.write(
                f"{len(orphans)} object(s) not referenced by any product:"
            )
            for key in orphans:
                self.stdout.write(f"  {key}")

    def _sync_product(
        self, product: BaseProduct, bucket: str, obj: dict[str, Any], dry_run: bool
    ) -> None:
        product.bucket = bucket
        product.s3_etag = (obj.get("ETag") or "").strip('"') or None
        product.s3_last_modified = obj.get("LastModified")
        product.file_size_bytes = obj.get("Size")
        product.is_uploaded = True
        if dry_run:
            self.stdout.write(
                f"[dry-run] would update {type(product).__name__} {product.pk} "
                f"from '{product.object_key}'"
            )
            return
        product.save(
            update_fields=[
                "bucket",
                "s3_etag",
                "s3_last_modified",
                "file_size_bytes",
                "is_uploaded",
                "updated_at",
            ]
        )
