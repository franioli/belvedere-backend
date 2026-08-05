"""Expose `points.active` as `is_active` on the views.

Placed immediately before `is_fixed` so the two flags read together. That means
a drop and recreate rather than `CREATE OR REPLACE VIEW`, which can only append
a trailing column, never insert one mid-list.

Reverse is a no-op: removing a view column also needs a drop and recreate, and
a spare column harms nothing — the unmanaged `PointsMeasurement` model simply
would not reference it. Any later migration that touches the views rebuilds
them from `surveys/sql.py` anyway.
"""

from django.db import migrations

from surveys.sql import CREATE_VIEWS, DROP_VIEWS


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0027_label_unique_ci"),
    ]

    operations = [
        migrations.RunSQL(
            sql=DROP_VIEWS + CREATE_VIEWS,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
