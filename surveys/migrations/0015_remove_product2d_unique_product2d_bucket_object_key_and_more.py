# Restructures Product2D and Product3D: drops S3 fields, adds wms_url / url,
# renames Flight fields from truncated legacy names.
#
# Written by hand because the live DB was partially migrated manually:
# S3 columns were already dropped and wms_url was already added to both tables
# (products_3d.wms_url must be renamed to products_3d.url).
# All DB-side operations use IF EXISTS / IF NOT EXISTS so the migration is safe
# to run against any state of the database.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0014_alter_activepoint_options_and_more"),
    ]

    operations = [
        # ── Constraint removals ──────────────────────────────────────────────
        migrations.RunSQL(
            sql="ALTER TABLE products_2d DROP CONSTRAINT IF EXISTS unique_product2d_bucket_object_key",
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="product2d",
                    name="unique_product2d_bucket_object_key",
                ),
            ],
        ),
        migrations.RunSQL(
            sql="ALTER TABLE products_3d DROP CONSTRAINT IF EXISTS unique_product3d_bucket_object_key",
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="product3d",
                    name="unique_product3d_bucket_object_key",
                ),
            ],
        ),
        # ── Flight field renames (not yet applied in live DB) ────────────────
        migrations.RenameField(
            model_name="flight", old_name="average_gs", new_name="average_gsd"
        ),
        migrations.RenameField(
            model_name="flight", old_name="average_he", new_name="average_height"
        ),
        migrations.RenameField(
            model_name="flight", old_name="camera_nam", new_name="camera_name"
        ),
        migrations.RenameField(
            model_name="flight", old_name="focal_leng", new_name="focal_length"
        ),
        migrations.RenameField(
            model_name="flight", old_name="global_acc", new_name="global_accuracy"
        ),
        migrations.RenameField(
            model_name="flight", old_name="n_checkpoi", new_name="n_checkpoints"
        ),
        migrations.RenameField(
            model_name="flight", old_name="n_controlp", new_name="n_controlpoints"
        ),
        migrations.RenameField(
            model_name="flight", old_name="sensor_siz", new_name="sensor_size"
        ),
        # ── Add wms_url to products_2d (may already exist in live DB) ────────
        migrations.RunSQL(
            sql="ALTER TABLE products_2d ADD COLUMN IF NOT EXISTS wms_url VARCHAR(1024)",
            reverse_sql="ALTER TABLE products_2d DROP COLUMN IF EXISTS wms_url",
            state_operations=[
                migrations.AddField(
                    model_name="product2d",
                    name="wms_url",
                    field=models.URLField(
                        blank=True,
                        help_text="WMS endpoint URL on GeoServer.",
                        max_length=1024,
                        null=True,
                    ),
                ),
            ],
        ),
        # ── Add url to products_3d ────────────────────────────────────────────
        # Live DB has a 'wms_url' column (added manually, wrong name).
        # Rename it to 'url' if that mapping hasn't been done yet;
        # fall back to ADD COLUMN if neither name exists.
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'products_3d' AND column_name = 'wms_url'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'products_3d' AND column_name = 'url'
                    ) THEN
                        ALTER TABLE products_3d RENAME COLUMN wms_url TO url;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'products_3d' AND column_name = 'url'
                    ) THEN
                        ALTER TABLE products_3d ADD COLUMN url VARCHAR(1024);
                    END IF;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.AddField(
                    model_name="product3d",
                    name="url",
                    field=models.URLField(
                        blank=True,
                        help_text="Direct URL to the COPC point cloud (Zenodo, S3, etc.).",
                        max_length=1024,
                        null=True,
                    ),
                ),
            ],
        ),
        # ── Update data_type help_text and FK related_name (state only) ──────
        migrations.AlterField(
            model_name="product2d",
            name="data_type",
            field=models.CharField(
                help_text="Product type, e.g. ortofoto, dsm.", max_length=64
            ),
        ),
        migrations.AlterField(
            model_name="product2d",
            name="survey",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products_2d",
                to="surveys.survey",
            ),
        ),
        migrations.AlterField(
            model_name="product3d",
            name="data_type",
            field=models.CharField(
                help_text="Product type, e.g. pointcloud, mesh.", max_length=64
            ),
        ),
        migrations.AlterField(
            model_name="product3d",
            name="survey",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products_3d",
                to="surveys.survey",
            ),
        ),
        # ── Remove S3 fields (IF EXISTS — already dropped in live DB) ────────
        migrations.RunSQL(
            sql="""
                ALTER TABLE products_2d
                    DROP COLUMN IF EXISTS bucket,
                    DROP COLUMN IF EXISTS file_size_bytes,
                    DROP COLUMN IF EXISTS is_uploaded,
                    DROP COLUMN IF EXISTS object_key,
                    DROP COLUMN IF EXISTS path,
                    DROP COLUMN IF EXISTS s3_etag,
                    DROP COLUMN IF EXISTS s3_last_modified;
            """,
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.RemoveField(model_name="product2d", name="bucket"),
                migrations.RemoveField(model_name="product2d", name="file_size_bytes"),
                migrations.RemoveField(model_name="product2d", name="is_uploaded"),
                migrations.RemoveField(model_name="product2d", name="object_key"),
                migrations.RemoveField(model_name="product2d", name="path"),
                migrations.RemoveField(model_name="product2d", name="s3_etag"),
                migrations.RemoveField(model_name="product2d", name="s3_last_modified"),
            ],
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE products_3d
                    DROP COLUMN IF EXISTS bucket,
                    DROP COLUMN IF EXISTS file_size_bytes,
                    DROP COLUMN IF EXISTS is_uploaded,
                    DROP COLUMN IF EXISTS object_key,
                    DROP COLUMN IF EXISTS path,
                    DROP COLUMN IF EXISTS s3_etag,
                    DROP COLUMN IF EXISTS s3_last_modified;
            """,
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[
                migrations.RemoveField(model_name="product3d", name="bucket"),
                migrations.RemoveField(model_name="product3d", name="file_size_bytes"),
                migrations.RemoveField(model_name="product3d", name="is_uploaded"),
                migrations.RemoveField(model_name="product3d", name="object_key"),
                migrations.RemoveField(model_name="product3d", name="path"),
                migrations.RemoveField(model_name="product3d", name="s3_etag"),
                migrations.RemoveField(model_name="product3d", name="s3_last_modified"),
            ],
        ),
    ]
