"""Rebase the ENU frame on RDN2008.

Follows the geometry re-tagging in `surveys/0022` and `image_index/0010`. Three
things change:

* `georef_to_enu` / `georef_from_enu` now go through EPSG:6705 (RDN2008
  geographic 3D) instead of 4979, so the chain is GRS80 end to end and never
  crosses a datum. Measured effect: `check_pipeline_route_equivalence` improves
  from 1.2e-04 m to ~1.3e-09 m, the GRS80/WGS84 ellipsoid discrepancy it used
  to report having disappeared.
* The frame origin is re-derived from D12's position *as RDN2008* rather than
  as WGS 84, and `base_srid` / `datum_epoch` are corrected. This moves every
  ENU coordinate by ~0.12 mm — the ellipsoid difference, not a datum shift.
* `spatial_ref_sys` is regenerated, because the pipeline text changes with the
  origin.

Doing this before the frame is frozen is free; afterwards it would require a
new SRID.
"""

from django.db import migrations, models

from georef.constants import (
    ENU_SRID,
    GEOGRAPHIC_2D_SRID,
    GEOGRAPHIC_3D_SRID,
    PROJECT_SRID,
)
from georef.crs import register_frame_crs
from georef.sql import (
    RECOMPUTE_CAMERAS_ENU,
    RECOMPUTE_MEASUREMENTS_ENU,
    transform_functions,
)

# Frozen origin of the frame: monument D12, unchanged numerically — only the
# CRS it is interpreted in changes.
ORIGIN_EAST = 416125.449
ORIGIN_NORTH = 5089423.209

PREVIOUS_SRID = 32632
PREVIOUS_GEOGRAPHIC_3D_SRID = 4979
DATUM_EPOCH = "2008.00"


def _rebase(apps, schema_editor, srid: int, geographic_3d: int, epoch: str | None):
    ReferenceFrame = apps.get_model("georef", "ReferenceFrame")

    frame = ReferenceFrame.objects.filter(srid=ENU_SRID).first()
    if frame is None:
        return
    if frame.frozen:
        raise RuntimeError(
            f"reference frame {ENU_SRID} is frozen; its origin cannot change. "
            f"Define a new SRID instead."
        )

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(transform_functions(geographic_3d))

        # Derive the origin rather than transcribe it, as in georef/0003.
        cursor.execute(
            "SELECT ST_X(g), ST_Y(g) FROM ("
            "  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), %s), %s) AS g"
            ") t",
            [ORIGIN_EAST, ORIGIN_NORTH, srid, GEOGRAPHIC_2D_SRID],
        )
        lon_0, lat_0 = cursor.fetchone()

    ReferenceFrame.objects.filter(srid=ENU_SRID).update(
        lat_0=lat_0, lon_0=lon_0, base_srid=srid, datum_epoch=epoch
    )
    frame.refresh_from_db()

    with schema_editor.connection.cursor() as cursor:
        register_frame_crs(cursor, frame)
        cursor.execute(RECOMPUTE_MEASUREMENTS_ENU, [ENU_SRID])
        cursor.execute(RECOMPUTE_CAMERAS_ENU, [ENU_SRID])


def to_rdn2008(apps, schema_editor):
    _rebase(apps, schema_editor, PROJECT_SRID, GEOGRAPHIC_3D_SRID, DATUM_EPOCH)


def to_wgs84(apps, schema_editor):
    _rebase(apps, schema_editor, PREVIOUS_SRID, PREVIOUS_GEOGRAPHIC_3D_SRID, None)


class Migration(migrations.Migration):
    dependencies = [
        ("georef", "0005_pyproj_crs_definition"),
        # the recompute statements read the re-tagged geometry columns
        ("surveys", "0022_rdn2008_srid"),
        ("image_index", "0010_rdn2008_srid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="referenceframe",
            name="base_srid",
            field=models.IntegerField(
                default=PROJECT_SRID,
                help_text="CRS the origin coordinates were taken from.",
            ),
        ),
        migrations.RunPython(to_rdn2008, to_wgs84),
    ]
