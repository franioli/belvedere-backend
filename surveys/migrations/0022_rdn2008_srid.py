"""Re-tag measurement geometry as RDN2008 / UTM 32N (EPSG:7791).

The coordinates were always RDN2008 — measured against the Italian permanent
network, ETRF2000 at epoch 2008.0 — but were labelled EPSG:32632, which names
the WGS 84 datum *ensemble* and its 2 m accuracy. This corrects the label; the
numbers do not move (`ST_SetSRID`, not `ST_Transform`).

`SeparateDatabaseAndState` is required: Django's own `AlterField` emits
`USING geom::geometry(POINT,7791)`, which PostGIS rejects because the cast does
not re-tag the SRID.

The four views have to be dropped first — Postgres refuses `ALTER COLUMN TYPE`
while a view depends on the column — and `compute_measurement_geometry()` has
to change with it, which finally brings it under migration control.
"""

import django.contrib.gis.db.models.fields
from django.db import migrations

from georef.constants import PROJECT_SRID
from surveys.sql import (
    DROP_VIEWS,
    compute_measurement_geometry,
    create_views,
    measurements_fill_geom_enu,
)

PREVIOUS_SRID = 32632

# This migration predates the ds_* -> std_* rename in surveys/0024, so on a
# fresh database the sigma columns are still named ds_* when it runs.
LEGACY_SIGMA_PREFIX = "ds"


def retag(srid: int) -> str:
    return f"""
{DROP_VIEWS}

ALTER TABLE measurements
    ALTER COLUMN geom TYPE geometry(Point, {srid})
    USING ST_SetSRID(geom, {srid});

{create_views(LEGACY_SIGMA_PREFIX)}
{compute_measurement_geometry(srid)}
{measurements_fill_geom_enu(srid)}
"""


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0021_alter_measurement_h"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="measurement",
                    name="geom",
                    field=django.contrib.gis.db.models.fields.PointField(
                        blank=True, null=True, srid=PROJECT_SRID
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=retag(PROJECT_SRID),
                    reverse_sql=retag(PREVIOUS_SRID),
                ),
            ],
        ),
    ]
