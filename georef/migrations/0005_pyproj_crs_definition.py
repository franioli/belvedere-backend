"""Regenerate the `spatial_ref_sys` row with PROJ-generated WKT.

The definition used to be a WKT2 template hand-written inside a Postgres
`format()` call. It is now produced by pyproj from the frame's parameters
(`georef.crs.crs_definition`), which is both readable and correct by
construction. The text differs, so the stored row has to be rewritten.

Coordinates are untouched — this only changes how the CRS is *described* to
QGIS and GDAL.
"""

from django.db import migrations

from georef.constants import ENU_SRID
from georef.crs import register_frame_crs


def regenerate_crs(apps, schema_editor):
    ReferenceFrame = apps.get_model("georef", "ReferenceFrame")
    frame = ReferenceFrame.objects.filter(srid=ENU_SRID).first()
    if frame is None:
        return
    with schema_editor.connection.cursor() as cursor:
        register_frame_crs(cursor, frame)


class Migration(migrations.Migration):
    dependencies = [
        ("georef", "0004_neutral_height_offset"),
    ]

    operations = [
        # No reverse: the CRS text is always regenerated from whatever
        # `georef.crs` currently produces, and unapplying 0004 rewrites it
        # anyway. There is no earlier text to restore.
        migrations.RunPython(regenerate_crs, migrations.RunPython.noop),
    ]
