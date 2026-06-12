from django.db import migrations

CREATE_FUNCTION = """
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
        -- Geometry changed → update coordinate columns from it
        NEW.easting   := ST_X(NEW.location);
        NEW.northing  := ST_Y(NEW.location);
        NEW.elevation := ST_Z(NEW.location);
    ELSIF (NEW.easting  IS DISTINCT FROM OLD.easting  OR
           NEW.northing IS DISTINCT FROM OLD.northing OR
           NEW.elevation IS DISTINCT FROM OLD.elevation) THEN
        -- Coordinate columns changed → rebuild geometry from them
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

CREATE_TRIGGER = """
CREATE TRIGGER camera_sync_location
BEFORE INSERT OR UPDATE ON image_index_camera
FOR EACH ROW EXECUTE FUNCTION image_index_camera_sync_location();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS camera_sync_location ON image_index_camera;"
DROP_FUNCTION = "DROP FUNCTION IF EXISTS image_index_camera_sync_location();"


class Migration(migrations.Migration):
    dependencies = [
        ("image_index", "0006_alter_image_preview_object_key"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_FUNCTION + CREATE_TRIGGER,
            reverse_sql=DROP_TRIGGER + DROP_FUNCTION,
        ),
    ]
