"""SQL surface of the reference frames: transformation functions + immutability.

`georef_to_enu` / `georef_from_enu` are the sanctioned conversions. They read
the generated `proj_pipeline` column, so they can never disagree with the
frame parameters.

The freeze guard lives in the database, not only in `ReferenceFrame.save()`,
because QGIS and psql write to this table directly.
"""

from django.db import migrations

from georef.constants import GEOGRAPHIC_3D_SRID

TO_ENU = f"""
CREATE OR REPLACE FUNCTION georef_to_enu(geom geometry, target_srid integer)
RETURNS geometry AS $$
    SELECT ST_TransformPipeline(
        ST_Transform(ST_Force3D($1), {GEOGRAPHIC_3D_SRID}),
        f.proj_pipeline,
        f.srid
    )
    FROM georef_reference_frame f
    WHERE f.srid = $2 AND $1 IS NOT NULL;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION georef_to_enu(geometry, integer) IS
'Transform a geometry into the local ENU frame identified by target_srid. '
'Returns NULL for NULL input or an unknown frame. Input is forced to 3D: a 2D '
'point entering a topocentric transform is meaningless.';
"""

FROM_ENU = f"""
CREATE OR REPLACE FUNCTION georef_from_enu(geom geometry, out_srid integer)
RETURNS geometry AS $$
    SELECT ST_Transform(
        ST_InverseTransformPipeline($1, f.proj_pipeline, {GEOGRAPHIC_3D_SRID}),
        $2
    )
    FROM georef_reference_frame f
    WHERE f.srid = ST_SRID($1) AND $1 IS NOT NULL;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION georef_from_enu(geometry, integer) IS
'Exact 3D inverse of georef_to_enu. This is the ONLY correct way back: the '
'spatial_ref_sys definition of the frame is +proj=ortho, which is right '
'horizontally but passes height through as ellipsoidal h, so ST_Transform on '
'an ENU geometry is wrong in Z by d^2/2R (0.7 m at 3 km).';
"""

FREEZE_GUARD = """
CREATE OR REPLACE FUNCTION georef_reference_frame_freeze()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.frozen THEN
            RAISE EXCEPTION
                'reference frame % is frozen and cannot be deleted; '
                'every coordinate stored in it would lose its meaning',
                OLD.srid;
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.frozen AND (
        NEW.lat_0 IS DISTINCT FROM OLD.lat_0 OR
        NEW.lon_0 IS DISTINCT FROM OLD.lon_0 OR
        NEW.h_0   IS DISTINCT FROM OLD.h_0   OR
        NEW.x_off IS DISTINCT FROM OLD.x_off OR
        NEW.y_off IS DISTINCT FROM OLD.y_off OR
        NEW.z_off IS DISTINCT FROM OLD.z_off OR
        NEW.ellps IS DISTINCT FROM OLD.ellps
    ) THEN
        RAISE EXCEPTION
            'reference frame % is frozen; define a new SRID instead', OLD.srid;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER reference_frame_freeze
BEFORE UPDATE OR DELETE ON georef_reference_frame
FOR EACH ROW EXECUTE FUNCTION georef_reference_frame_freeze();
"""

DROP = """
DROP TRIGGER IF EXISTS reference_frame_freeze ON georef_reference_frame;
DROP FUNCTION IF EXISTS georef_reference_frame_freeze();
DROP FUNCTION IF EXISTS georef_from_enu(geometry, integer);
DROP FUNCTION IF EXISTS georef_to_enu(geometry, integer);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("georef", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=TO_ENU + FROM_ENU + FREEZE_GUARD, reverse_sql=DROP),
    ]
