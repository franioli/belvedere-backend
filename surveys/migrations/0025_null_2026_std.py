"""Clear the 2026 standard deviations — they hold displacements.

The 2026 campaign was entered with displacements in the sigma columns: 30 of
its 31 non-null rows are negative, which is impossible for a standard
deviation. 2015-2025 are clean (527 of 557 rows are plausible sigmas, all
non-negative and <= 0.1 m).

All 2026 rows are cleared, not just the negative ones — the remainder of that
campaign is no more trustworthy than the rest of it.

No reverse: the values were displacements, which are already computed in
`points_movement_*`, so restoring them would only reintroduce the error. The
originals are in db-backups/belvedere_20260805_110910.dump if ever needed.
"""

from django.db import migrations

CLEAR_2026 = """
UPDATE measurements
   SET std_east = NULL, std_north = NULL, std_h = NULL
 WHERE survey IN (SELECT id FROM surveys WHERE year = 2026);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0024_rename_ds_to_std"),
    ]

    operations = [
        migrations.RunSQL(sql=CLEAR_2026, reverse_sql=migrations.RunSQL.noop),
    ]
