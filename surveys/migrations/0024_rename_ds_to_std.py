"""Rename `ds_east`/`ds_north`/`ds_h` to `std_east`/`std_north`/`std_h`.

They are standard deviations in metres — the import help page always said so —
but the name read like "delta s" and invited confusion with the displacements
in `points_movement_*`.

The views have to be dropped and recreated, not replaced: a view's output
column name is fixed at creation, and `CREATE OR REPLACE VIEW` cannot rename
one. Postgres would keep exposing `ds_east` on `points_measurements` otherwise.

Breaking for API consumers — `GET /surveys/measurements/` now returns `std_*`.
The web-map was updated in the same release.
"""

from django.db import migrations

from surveys.sql import CREATE_VIEWS, DROP_VIEWS, create_views

#: The same view DDL against the pre-rename column names, so unapplying this
#: migration rebuilds views that match the reverted table.
LEGACY_CREATE_VIEWS = create_views("ds")


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0023_datum_metadata"),
    ]

    operations = [
        # Views first: they reference the columns about to be renamed.
        migrations.RunSQL(sql=DROP_VIEWS, reverse_sql=LEGACY_CREATE_VIEWS),
        migrations.RenameField(
            model_name="measurement", old_name="ds_east", new_name="std_east"
        ),
        migrations.RenameField(
            model_name="measurement", old_name="ds_north", new_name="std_north"
        ),
        migrations.RenameField(
            model_name="measurement", old_name="ds_h", new_name="std_h"
        ),
        migrations.RunSQL(sql=CREATE_VIEWS, reverse_sql=DROP_VIEWS),
    ]
