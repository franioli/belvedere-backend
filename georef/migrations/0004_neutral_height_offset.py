"""Lift U off the tangent plane with a neutral height offset.

With `z_off = 0`, U is signed height above the tangent plane at D12, so every
point below the monument came out negative (-289.35 .. +170.99 over the survey
data).

`z_off = 1000` is deliberately **not** altitude-like. Setting `z_off = h_0`
would have made U read 1832..2292, close to the ellipsoidal height but up to
0.295 m below it (the `d^2/2R` tangent-plane term) — a number that looks like
an altitude while not being one, which is precisely the trap already documented
for the ortho display CRS. A synthetic offset cannot be misread. Exact heights
remain available in `measurements.h` and `h_orto`.

1000 rather than a smaller value because `z_off` is permanent once the frame is
frozen: it keeps U positive down to ~1121 m ellipsoidal, covering the glacier
and the valley floor below it.

E and N are untouched — moving the origin along the ellipsoid normal is a pure
U translation (verified: E/N shift by 2.7e-10 m).
"""

from django.db import migrations

from georef.constants import ENU_SRID
from georef.sql import (
    RECOMPUTE_CAMERAS_ENU,
    RECOMPUTE_MEASUREMENTS_ENU,
    SPATIAL_REF_SYS_UPSERT,
)

Z_OFF = 1000.0
PREVIOUS_Z_OFF = 0.0


def _set_z_off(apps, schema_editor, value: float) -> None:
    ReferenceFrame = apps.get_model("georef", "ReferenceFrame")

    frame = ReferenceFrame.objects.filter(srid=ENU_SRID).first()
    if frame is None:
        return
    if frame.frozen:
        raise RuntimeError(
            f"reference frame {ENU_SRID} is frozen; its offsets cannot change. "
            f"Define a new SRID instead."
        )

    # The generated `proj_pipeline` column recomputes itself on UPDATE.
    ReferenceFrame.objects.filter(srid=ENU_SRID).update(z_off=value)

    with schema_editor.connection.cursor() as cursor:
        # The ortho proj4text carries no z, but the srtext REMARK embeds the
        # pipeline and would otherwise still advertise the old zoff.
        cursor.execute(SPATIAL_REF_SYS_UPSERT, [ENU_SRID])
        cursor.execute(RECOMPUTE_MEASUREMENTS_ENU, [ENU_SRID])
        cursor.execute(RECOMPUTE_CAMERAS_ENU, [ENU_SRID])


def apply_offset(apps, schema_editor):
    _set_z_off(apps, schema_editor, Z_OFF)


def revert_offset(apps, schema_editor):
    _set_z_off(apps, schema_editor, PREVIOUS_Z_OFF)


class Migration(migrations.Migration):
    dependencies = [
        ("georef", "0003_belvedere_frame"),
        # the recompute statements write columns these two create
        ("surveys", "0020_measurement_geom_enu"),
        ("image_index", "0009_camera_location_enu"),
    ]

    operations = [
        migrations.RunPython(apply_offset, revert_offset),
    ]
