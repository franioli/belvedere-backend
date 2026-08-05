"""Materialise measurement positions in the local ENU frame.

`geom_enu` is stored rather than computed on the fly: `georef_to_enu` is only
STABLE (it reads `georef_reference_frame`), so a generated column is not an
option, and every query would otherwise pay for the transform.

The trigger reads `east`/`north`/`h` directly rather than `geom`, because
`geom` is 2D and because `compute_measurement_geometry_trigger` is not under
migration control — depending on it would make the ENU column silently NULL on
fresh databases and couple us to trigger firing order.
"""

import django.contrib.gis.db.models.fields
from django.db import migrations

from georef.constants import ENU_SRID, PROJECT_SRID

FILL_ENU = f"""
CREATE OR REPLACE FUNCTION measurements_fill_geom_enu()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.east IS NULL OR NEW.north IS NULL OR NEW.h IS NULL THEN
        NEW.geom_enu := NULL;
    ELSE
        NEW.geom_enu := georef_to_enu(
            ST_SetSRID(ST_MakePoint(NEW.east, NEW.north, NEW.h), {PROJECT_SRID}),
            {ENU_SRID}
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER measurements_fill_geom_enu
BEFORE INSERT OR UPDATE OF east, north, h ON measurements
FOR EACH ROW EXECUTE FUNCTION measurements_fill_geom_enu();
"""

DROP_ENU = """
DROP TRIGGER IF EXISTS measurements_fill_geom_enu ON measurements;
DROP FUNCTION IF EXISTS measurements_fill_geom_enu();
"""

BACKFILL = f"""
UPDATE measurements
   SET geom_enu = georef_to_enu(
           ST_SetSRID(ST_MakePoint(east, north, h), {PROJECT_SRID}),
           {ENU_SRID}
       )
 WHERE east IS NOT NULL AND north IS NOT NULL AND h IS NOT NULL;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0019_point_created_at"),
        ("georef", "0003_belvedere_frame"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="geom_enu",
            field=django.contrib.gis.db.models.fields.PointField(
                blank=True,
                dim=3,
                editable=False,
                help_text=(
                    "Position in the local ENU frame, filled by a database "
                    "trigger from east/north/h. Read-only: edit the source "
                    "coordinates instead."
                ),
                null=True,
                srid=ENU_SRID,
            ),
        ),
        migrations.RunSQL(sql=FILL_ENU, reverse_sql=DROP_ENU),
        migrations.RunSQL(
            sql=BACKFILL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
