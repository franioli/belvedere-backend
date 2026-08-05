"""Materialise camera positions in the local ENU frame.

The ENU fill is folded into the *existing* `image_index_camera_sync_location()`
function rather than added as a second trigger: Postgres fires BEFORE-row
triggers in name order, so a separate trigger would run before or after the
location sync depending on its name and could read a stale `location`. One
function, one pass, no ordering trap.
"""

import django.contrib.gis.db.models.fields
from django.db import migrations

from georef.constants import ENU_SRID

SYNC_WITH_ENU = f"""
CREATE OR REPLACE FUNCTION image_index_camera_sync_location()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.location IS NOT NULL THEN
            NEW.easting  := ST_X(NEW.location);
            NEW.northing := ST_Y(NEW.location);
            NEW.elevation := ST_Z(NEW.location);
        ELSIF NEW.easting IS NOT NULL AND NEW.northing IS NOT NULL THEN
            NEW.location := ST_SetSRID(
                ST_MakePoint(NEW.easting, NEW.northing, COALESCE(NEW.elevation, 0)),
                NEW.epsg_code
            );
        END IF;
    ELSIF NEW.location IS DISTINCT FROM OLD.location THEN
        -- Geometry changed -> update coordinate columns from it
        NEW.easting   := ST_X(NEW.location);
        NEW.northing  := ST_Y(NEW.location);
        NEW.elevation := ST_Z(NEW.location);
    ELSIF (NEW.easting  IS DISTINCT FROM OLD.easting  OR
           NEW.northing IS DISTINCT FROM OLD.northing OR
           NEW.elevation IS DISTINCT FROM OLD.elevation) THEN
        -- Coordinate columns changed -> rebuild geometry from them
        IF NEW.easting IS NOT NULL AND NEW.northing IS NOT NULL THEN
            NEW.location := ST_SetSRID(
                ST_MakePoint(NEW.easting, NEW.northing, COALESCE(NEW.elevation, 0)),
                NEW.epsg_code
            );
        END IF;
    END IF;

    NEW.location_enu := georef_to_enu(NEW.location, {ENU_SRID});

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Body as of image_index/0007_camera_sync_location_trigger.py, restored on reverse.
SYNC_WITHOUT_ENU = """
CREATE OR REPLACE FUNCTION image_index_camera_sync_location()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.location IS NOT NULL THEN
            NEW.easting  := ST_X(NEW.location);
            NEW.northing := ST_Y(NEW.location);
            NEW.elevation := ST_Z(NEW.location);
        ELSIF NEW.easting IS NOT NULL AND NEW.northing IS NOT NULL THEN
            NEW.location := ST_SetSRID(
                ST_MakePoint(NEW.easting, NEW.northing, COALESCE(NEW.elevation, 0)),
                NEW.epsg_code
            );
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.location IS DISTINCT FROM OLD.location THEN
        NEW.easting   := ST_X(NEW.location);
        NEW.northing  := ST_Y(NEW.location);
        NEW.elevation := ST_Z(NEW.location);
    ELSIF (NEW.easting  IS DISTINCT FROM OLD.easting  OR
           NEW.northing IS DISTINCT FROM OLD.northing OR
           NEW.elevation IS DISTINCT FROM OLD.elevation) THEN
        IF NEW.easting IS NOT NULL AND NEW.northing IS NOT NULL THEN
            NEW.location := ST_SetSRID(
                ST_MakePoint(NEW.easting, NEW.northing, COALESCE(NEW.elevation, 0)),
                NEW.epsg_code
            );
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

BACKFILL = f"""
UPDATE image_index_camera
   SET location_enu = georef_to_enu(location, {ENU_SRID})
 WHERE location IS NOT NULL;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("image_index", "0008_camera_resolution_mpx_camera_sensor_height_and_more"),
        ("georef", "0003_belvedere_frame"),
    ]

    operations = [
        migrations.AddField(
            model_name="camera",
            name="location_enu",
            field=django.contrib.gis.db.models.fields.PointField(
                blank=True,
                dim=3,
                editable=False,
                help_text=(
                    "Camera location in the local ENU frame, filled by a "
                    "database trigger from `location`. Read-only: edit "
                    "`location` instead."
                ),
                null=True,
                srid=ENU_SRID,
            ),
        ),
        migrations.RunSQL(sql=SYNC_WITH_ENU, reverse_sql=SYNC_WITHOUT_ENU),
        migrations.RunSQL(sql=BACKFILL, reverse_sql=migrations.RunSQL.noop),
    ]
