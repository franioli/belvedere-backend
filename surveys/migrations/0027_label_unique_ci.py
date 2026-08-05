"""Make point labels unique case-insensitively.

`points.label` already had a unique index, but a case-sensitive one — which is
how the 2026 CSV import created `D01BIS` alongside the existing `D01bis`,
splitting that stake's history and costing it its displacement in
`points_movement_*`.

Existing duplicates have to be merged first, so this checks and stops with
instructions rather than failing on an opaque index violation.
"""

import django.db.models.functions.text
from django.db import migrations, models

CHECK_DUPLICATES = """
SELECT lower(trim(label)), count(*)
FROM points GROUP BY 1 HAVING count(*) > 1 ORDER BY 1
"""


def refuse_if_duplicates(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(CHECK_DUPLICATES)
        duplicates = cursor.fetchall()
    if duplicates:
        listed = ", ".join(f"{label} x{count}" for label, count in duplicates[:10])
        raise RuntimeError(
            f"{len(duplicates)} label(s) differ only by case or whitespace: "
            f"{listed}. Merge them before applying this constraint:\n"
            f"    manage.py merge_duplicate_points            # review\n"
            f"    manage.py merge_duplicate_points --apply"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0026_field_metadata"),
    ]

    operations = [
        migrations.RunPython(refuse_if_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="point",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim("label")
                ),
                name="points_label_unique_ci",
            ),
        ),
    ]
