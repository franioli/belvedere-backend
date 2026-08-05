"""Insert the Belvedere ENU frame and register it in `spatial_ref_sys`.

Origin: GNSS monument **D12**, frozen at its campaign-mean UTM 32N position.
lat_0/lon_0 are *derived* here with PostGIS rather than transcribed, so the
frame carries the full double precision of the conversion.

The `spatial_ref_sys` row is built by INSERT ... SELECT from the frame row, so
the two cannot drift. It is DML on a PostGIS-owned table — no DDL is applied.

Note the row uses **+proj=ortho**, not +proj=topocentric: PROJ 9.6 cannot
compose geographic -> topocentric as a CRS ("Mismatched units between step 2
and 3") and drops the origin from the topocentric WKT2. Orthographic about the
same origin is horizontally identical to well under a millimetre at this
extent, and is what QGIS and GDAL can actually consume. Height is the caveat:
see the comment on `georef_from_enu`.
"""

from django.db import migrations

from georef.constants import BELVEDERE_FRAME_NAME, ENU_SRID, PROJECT_SRID

# Frozen origin: campaign-mean position of monument D12 in EPSG:32632,
# ellipsoidal height. Recorded here because this is the one number the whole
# frame depends on.
ORIGIN_MARK = "D12"
ORIGIN_EAST = 416125.449
ORIGIN_NORTH = 5089423.209
ORIGIN_H = 2121.172

FALSE_ORIGIN = (10000.0, 10000.0, 0.0)
ELLPS = "GRS80"

DESCRIPTION = (
    "Belvedere Glacier local topocentric ENU frame. Origin on GNSS monument "
    f"{ORIGIN_MARK}, false origin +{FALSE_ORIGIN[0]:.0f} m East / "
    f"+{FALSE_ORIGIN[1]:.0f} m North so all coordinates are positive and "
    "5-digit. An exact rigid motion of ECEF: distances and angles are true, "
    "no grid scale factor, no convergence. Heights are ellipsoidal, measured "
    "from the tangent plane at the origin."
)

NOTES = (
    "spatial_ref_sys carries a +proj=ortho definition for QGIS/GDAL: exact "
    "horizontally (<1 mm over the glacier) but NOT in Z. Use georef_from_enu() "
    "for the 3D inverse. Frozen frames are immutable — corrections need a new "
    "SRID."
)

INSERT_SPATIAL_REF_SYS = """
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext)
SELECT
    f.srid,
    'BELVEDERE',
    f.srid,
    format(
        '+proj=ortho +lat_0=%%s +lon_0=%%s +x_0=%%s +y_0=%%s +ellps=%%s +units=m +no_defs',
        f.lat_0::text, f.lon_0::text, f.x_off::text, f.y_off::text, f.ellps
    ),
    format(
        'PROJCRS["%%s",BASEGEOGCRS["unknown",'
        'DATUM["Unknown based on GRS 1980 ellipsoid",'
        'ELLIPSOID["GRS 1980",6378137,298.257222101,LENGTHUNIT["metre",1],ID["EPSG",7019]]],'
        'PRIMEM["Greenwich",0,ANGLEUNIT["degree",0.0174532925199433],ID["EPSG",8901]]],'
        'CONVERSION["unknown",METHOD["Orthographic",ID["EPSG",9840]],'
        'PARAMETER["Latitude of natural origin",%%s,ANGLEUNIT["degree",0.0174532925199433],ID["EPSG",8801]],'
        'PARAMETER["Longitude of natural origin",%%s,ANGLEUNIT["degree",0.0174532925199433],ID["EPSG",8802]],'
        'PARAMETER["False easting",%%s,LENGTHUNIT["metre",1],ID["EPSG",8806]],'
        'PARAMETER["False northing",%%s,LENGTHUNIT["metre",1],ID["EPSG",8807]]],'
        'CS[Cartesian,2],'
        'AXIS["(E)",east,ORDER[1],LENGTHUNIT["metre",1,ID["EPSG",9001]]],'
        'AXIS["(N)",north,ORDER[2],LENGTHUNIT["metre",1,ID["EPSG",9001]]],'
        'REMARK["Horizontal display definition for the topocentric ENU frame %%s. '
        'True 3D pipeline: %%s . Z stored in this CRS is height above the tangent '
        'plane, NOT ellipsoidal h; use georef_from_enu() to invert."]]',
        f.name, f.lat_0::text, f.lon_0::text, f.x_off::text, f.y_off::text,
        f.name, f.proj_pipeline
    )
FROM georef_reference_frame f
WHERE f.srid = %s
ON CONFLICT (srid) DO UPDATE
    SET auth_name = EXCLUDED.auth_name,
        auth_srid = EXCLUDED.auth_srid,
        proj4text = EXCLUDED.proj4text,
        srtext    = EXCLUDED.srtext;
"""


def create_frame(apps, schema_editor):
    ReferenceFrame = apps.get_model("georef", "ReferenceFrame")
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_X(g), ST_Y(g) FROM ("
            "  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), %s), 4326) AS g"
            ") t",
            [ORIGIN_EAST, ORIGIN_NORTH, PROJECT_SRID],
        )
        lon_0, lat_0 = cursor.fetchone()

    ReferenceFrame.objects.update_or_create(
        srid=ENU_SRID,
        defaults={
            "name": BELVEDERE_FRAME_NAME,
            "description": DESCRIPTION,
            "origin_mark": ORIGIN_MARK,
            "lat_0": lat_0,
            "lon_0": lon_0,
            "h_0": ORIGIN_H,
            "ellps": ELLPS,
            "x_off": FALSE_ORIGIN[0],
            "y_off": FALSE_ORIGIN[1],
            "z_off": FALSE_ORIGIN[2],
            "base_srid": PROJECT_SRID,
            "frozen": False,
            "notes": NOTES,
        },
    )

    with connection.cursor() as cursor:
        cursor.execute(INSERT_SPATIAL_REF_SYS, [ENU_SRID])


def drop_frame(apps, schema_editor):
    ReferenceFrame = apps.get_model("georef", "ReferenceFrame")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DELETE FROM spatial_ref_sys WHERE srid = %s", [ENU_SRID])
    ReferenceFrame.objects.filter(srid=ENU_SRID).update(frozen=False)
    ReferenceFrame.objects.filter(srid=ENU_SRID).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("georef", "0002_frame_functions"),
    ]

    operations = [
        migrations.RunPython(create_frame, drop_frame),
    ]
