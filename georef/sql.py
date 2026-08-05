"""SQL that derives state from a reference frame.

Kept in one place because it is run from more than one migration and from the
`recompute_enu` command: the `spatial_ref_sys` row and the materialised ENU
geometries are *derived*, so every regeneration must use identical SQL or they
drift apart.

Each statement takes the frame SRID as its single parameter.
"""

from georef.constants import PROJECT_SRID

#: Rebuild the `spatial_ref_sys` row from the frame. DML on a PostGIS-owned
#: table — no DDL. `%%s` are Postgres `format()` placeholders; the single `%s`
#: is the query parameter.
SPATIAL_REF_SYS_UPSERT = """
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
        'REMARK["Horizontal DISPLAY definition for the topocentric ENU frame %%s, '
        'for QGIS and GDAL only - it is NOT interchangeable with the frame. '
        'Reprojecting through it is off by h*d/N horizontally (~0.7 m over the '
        'glacier, because ortho ignores ellipsoidal height) and by d^2/2R in Z '
        '(~0.36 m, because ortho passes h through while the frame stores height '
        'above the tangent plane). Z is also shifted by the frame zoff and is NOT '
        'an altitude. Keep the project CRS on this SRID so nothing reprojects, and '
        'use georef_from_enu() for the exact 3D inverse. True 3D pipeline: %%s"]]',
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

#: Re-derive `measurements.geom_enu` from the source coordinates. Reads
#: east/north/h rather than `geom`, which is 2D.
RECOMPUTE_MEASUREMENTS_ENU = f"""
UPDATE measurements
   SET geom_enu = georef_to_enu(
           ST_SetSRID(ST_MakePoint(east, north, h), {PROJECT_SRID}), %s)
 WHERE east IS NOT NULL AND north IS NOT NULL AND h IS NOT NULL;
"""

#: Re-derive `image_index_camera.location_enu` from `location`.
RECOMPUTE_CAMERAS_ENU = """
UPDATE image_index_camera
   SET location_enu = georef_to_enu(location, %s)
 WHERE location IS NOT NULL;
"""

#: Rows still missing an ENU geometry, for `recompute_enu --dry-run`.
COUNT_MISSING_MEASUREMENTS_ENU = (
    "SELECT count(*) FROM measurements WHERE geom_enu IS NULL"
)
COUNT_MISSING_CAMERAS_ENU = (
    "SELECT count(*) FROM image_index_camera "
    "WHERE location IS NOT NULL AND location_enu IS NULL"
)
