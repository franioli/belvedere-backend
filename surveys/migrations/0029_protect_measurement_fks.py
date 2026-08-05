"""`Measurement.point` / `.survey` become PROTECT instead of DO_NOTHING.

`DO_NOTHING` meant Django issued the DELETE without checking, so removing a
point in the admin surfaced a bare `IntegrityError` 500 from Postgres. PROTECT
turns that into a readable "cannot delete, it is referenced by" message, and
`PointAdmin.delete_with_measurements` is the deliberate way through.

`on_delete` is Django-side only, so those two are state changes with no SQL.
The `h` field is here just because its comment text changed — and it needs
`SeparateDatabaseAndState`, because Django's `AlterField` re-emits
`ALTER COLUMN ... TYPE`, which Postgres refuses on `h`: the
`measurements_fill_geom_enu` trigger is declared `UPDATE OF east, north, h`.
"""

import django.db.models.deletion
from django.db import migrations, models

from surveys.sql import comment_columns


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0028_points_measurements_is_active"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="measurement",
                    name="h",
                    field=models.FloatField(
                        db_comment="Ellipsoidal height, m (GRS80).",
                        verbose_name="h (ellipsoidal)",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=comment_columns("measurements", ("h",)),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
        migrations.AlterField(
            model_name="measurement",
            name="point",
            field=models.ForeignKey(
                db_column="point",
                on_delete=django.db.models.deletion.PROTECT,
                to="surveys.point",
            ),
        ),
        migrations.AlterField(
            model_name="measurement",
            name="survey",
            field=models.ForeignKey(
                db_column="survey",
                on_delete=django.db.models.deletion.PROTECT,
                to="surveys.survey",
            ),
        ),
    ]
