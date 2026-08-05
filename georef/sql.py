"""SQL that derives state from a reference frame.

Kept in one place because it is run from more than one migration and from the
`recompute_enu` command: the `spatial_ref_sys` row and the materialised ENU
geometries are *derived*, so every regeneration must use identical SQL or they
drift apart.

Each statement takes the frame SRID as its single parameter.
"""

from georef.constants import PROJECT_SRID

#: Rebuild the `spatial_ref_sys` row. DML on a PostGIS-owned table — no DDL.
#: Parameters: srid, srid, proj4text, srtext — the last two from
#: `georef.crs.crs_definition()`.
SPATIAL_REF_SYS_UPSERT = """
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext)
VALUES (%s, 'BELVEDERE', %s, %s, %s)
ON CONFLICT (srid) DO UPDATE
    SET auth_name = EXCLUDED.auth_name,
        auth_srid = EXCLUDED.auth_srid,
        proj4text = EXCLUDED.proj4text,
        srtext    = EXCLUDED.srtext;
"""

#: What is currently registered, for the drift check.
SPATIAL_REF_SYS_SELECT = "SELECT proj4text, srtext FROM spatial_ref_sys WHERE srid = %s"

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
