"""Re-tag camera locations as RDN2008 / UTM 32N (EPSG:7791).

Same correction as `surveys/0022`, and the same reason for
`SeparateDatabaseAndState`. No view depends on this column, so no drops are
needed. `epsg_code` is data rather than schema, so it is updated in place.
"""

import django.contrib.gis.db.models.fields
from django.db import migrations, models

from georef.constants import PROJECT_SRID

PREVIOUS_SRID = 32632


def retag(srid: int, previous: int) -> str:
    return f"""
ALTER TABLE image_index_camera
    ALTER COLUMN location TYPE geometry(PointZ, {srid})
    USING ST_SetSRID(location, {srid});

UPDATE image_index_camera SET epsg_code = {srid} WHERE epsg_code = {previous};
"""


class Migration(migrations.Migration):
    dependencies = [
        ("image_index", "0009_camera_location_enu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="camera",
            name="epsg_code",
            field=models.IntegerField(
                default=PROJECT_SRID,
                help_text=(
                    "EPSG code of the coordinate reference system used for "
                    "location fields."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="camera",
            name="easting",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="Camera easting in the project CRS, usually EPSG:7791.",
            ),
        ),
        migrations.AlterField(
            model_name="camera",
            name="northing",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="Camera northing in the project CRS, usually EPSG:7791.",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="camera",
                    name="location",
                    field=django.contrib.gis.db.models.fields.PointField(
                        blank=True,
                        dim=3,
                        null=True,
                        srid=PROJECT_SRID,
                        help_text=(
                            "3D camera location as a PostGIS point geometry in "
                            "the project CRS."
                        ),
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=retag(PROJECT_SRID, PREVIOUS_SRID),
                    reverse_sql=retag(PREVIOUS_SRID, PROJECT_SRID),
                ),
            ],
        ),
    ]
