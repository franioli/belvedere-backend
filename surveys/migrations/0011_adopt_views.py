"""Adopt the surviving Postgres views into Django migrations.

The views were created manually in the database (QGIS layer sources). From
this migration on, their DDL is version-controlled and they exist on fresh
databases too. `CREATE OR REPLACE` is a no-op on the live DB. Future changes
to a view must go through a new migration.

`points_summary` (the renamed legacy `public.points` aggregate view) is
dropped: the Django admin computes the same aggregates via annotations.
"""

from django.db import migrations

POINTS_MEASUREMENTS_SQL = """
CREATE OR REPLACE VIEW public.points_measurements AS
 SELECT meas.id,
    meas.geom,
    pts.label,
    meas.point AS point_id,
    pts.is_fixed,
    meas.east,
    meas.north,
    meas.h_orto,
    meas.lat,
    meas.lon,
    meas.h,
    meas.survey AS survey_id,
    sur.date AS survey_date,
    sur.year AS survey_year,
    meas.meas_date,
    meas.meas_time,
    meas.meas_strategy,
    meas.ds_east,
    meas.ds_north,
    meas.ds_h
   FROM measurements meas
     JOIN surveys sur ON meas.survey = sur.id
     JOIN points pts ON meas.point = pts.id
  ORDER BY sur.year DESC, pts.label;
"""

POINTS_MOVEMENT_RAW_SQL = """
CREATE OR REPLACE VIEW public.points_movement_raw AS
 WITH laggedmeasurements AS (
         SELECT meas_1.id,
            lag(meas_1.east) OVER (PARTITION BY meas_1.label ORDER BY meas_1.survey_date) AS prev_east,
            lag(meas_1.north) OVER (PARTITION BY meas_1.label ORDER BY meas_1.survey_date) AS prev_north,
            lag(meas_1.h) OVER (PARTITION BY meas_1.label ORDER BY meas_1.survey_date) AS prev_h,
            lag(meas_1.survey_date) OVER (PARTITION BY meas_1.label ORDER BY meas_1.survey_date) AS prev_survey_date
           FROM points_measurements meas_1
        ), diffs AS (
         SELECT meas_1.id,
            COALESCE(meas_1.survey_date - lm_1.prev_survey_date, 0) AS dt,
            COALESCE(meas_1.east - lm_1.prev_east, 0::double precision) AS d_e,
            COALESCE(meas_1.north - lm_1.prev_north, 0::double precision) AS d_n,
            COALESCE(meas_1.h - lm_1.prev_h, 0::double precision) AS d_h
           FROM points_measurements meas_1
             JOIN laggedmeasurements lm_1 ON meas_1.id = lm_1.id
        )
 SELECT meas.id,
    meas.geom,
    meas.label,
    meas.survey_year,
    meas.is_fixed,
    meas.survey_date AS survey_date_fin,
    lm.prev_survey_date AS survey_date_prev,
    diffs.dt,
    meas.east AS east_fin,
    meas.north AS north_fin,
    meas.h AS h_fin,
    lm.prev_east AS east_prev,
    lm.prev_north AS north_prev,
    lm.prev_h AS h_prev,
    diffs.d_e,
    diffs.d_n,
    diffs.d_h,
    COALESCE(sqrt(pow(diffs.d_e, 2::double precision) + pow(diffs.d_n, 2::double precision) + pow(diffs.d_h, 2::double precision)), 0::double precision) AS d,
    COALESCE(diffs.d_e / NULLIF(diffs.dt, 0)::double precision, 0::double precision) AS v_e,
    COALESCE(diffs.d_n / NULLIF(diffs.dt, 0)::double precision, 0::double precision) AS v_n,
    COALESCE(diffs.d_h / NULLIF(diffs.dt, 0)::double precision, 0::double precision) AS v_h,
    COALESCE(sqrt(pow(diffs.d_e, 2::double precision) + pow(diffs.d_n, 2::double precision) + pow(diffs.d_h, 2::double precision)) / NULLIF(diffs.dt, 0)::double precision, 0::double precision) AS v,
    COALESCE(diffs.d_e / NULLIF(pow(diffs.dt::double precision, 2::double precision), 0::double precision), 0::double precision) AS a_e,
    COALESCE(diffs.d_n / NULLIF(pow(diffs.dt::double precision, 2::double precision), 0::double precision), 0::double precision) AS a_n,
    COALESCE(diffs.d_h / NULLIF(pow(diffs.dt::double precision, 2::double precision), 0::double precision), 0::double precision) AS a_h,
    COALESCE(sqrt(pow(diffs.d_e, 2::double precision) + pow(diffs.d_n, 2::double precision) + pow(diffs.d_h, 2::double precision)) / NULLIF(pow(diffs.dt::double precision, 2::double precision), 0::double precision), 0::double precision) AS a
   FROM points_measurements meas
     JOIN laggedmeasurements lm ON meas.id = lm.id
     JOIN diffs ON meas.id = diffs.id;
"""

POINTS_MOVEMENT_FILTERED_SQL = """
CREATE OR REPLACE VIEW public.points_movement_filtered AS
 SELECT id,
    geom,
    label,
    survey_year,
    is_fixed,
    survey_date_fin,
    survey_date_prev,
    dt,
    east_fin,
    north_fin,
    h_fin,
    east_prev,
    north_prev,
    h_prev,
    d_e,
    d_n,
    d_h,
    d,
    v_e,
    v_n,
    v_h,
    v,
    a_e,
    a_n,
    a_h,
    a
   FROM points_movement_raw
  WHERE is_fixed = false AND dt > 280 AND dt < 400 AND d > 0::double precision
  ORDER BY label, survey_date_fin DESC;
"""

ACTIVE_POINTS_SQL = """
CREATE OR REPLACE VIEW public.active_points AS
 WITH lastmeasurement AS (
         SELECT meas.id AS meas_id,
            meas.geom,
            points.label,
            surveys.date AS last_measure_date,
            meas.east,
            meas.north,
            meas.h,
            points.is_fixed,
            row_number() OVER (PARTITION BY points.label ORDER BY surveys.date DESC) AS row_num
           FROM measurements meas
             JOIN points ON meas.point = points.id
             JOIN surveys ON meas.survey = surveys.id
          WHERE points.active = true
        )
 SELECT meas_id,
    geom,
    label,
    last_measure_date,
    east,
    north,
    h,
    is_fixed
   FROM lastmeasurement
  WHERE row_num = 1;
"""

POINTS_SUMMARY_SQL = """
CREATE OR REPLACE VIEW public.points_summary AS
 SELECT p.id,
    p.label,
    p.active,
    p.is_fixed,
    p.ref_date,
    min(sur.date) AS first_survey_date,
    max(sur.date) AS last_survey_date,
    count(m.id) AS num_measurements,
    p.notes
   FROM points p
     LEFT JOIN measurements m ON p.id = m.point
     LEFT JOIN surveys sur ON m.survey = sur.id
  GROUP BY p.id, p.label, p.active, p.is_fixed
  ORDER BY p.label;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0010_volume_product2d_product3d"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP VIEW IF EXISTS public.points_summary;",
            reverse_sql=POINTS_SUMMARY_SQL,
        ),
        migrations.RunSQL(
            sql=POINTS_MEASUREMENTS_SQL,
            reverse_sql="DROP VIEW IF EXISTS public.points_measurements CASCADE;",
        ),
        migrations.RunSQL(
            sql=POINTS_MOVEMENT_RAW_SQL,
            reverse_sql="DROP VIEW IF EXISTS public.points_movement_raw CASCADE;",
        ),
        migrations.RunSQL(
            sql=POINTS_MOVEMENT_FILTERED_SQL,
            reverse_sql="DROP VIEW IF EXISTS public.points_movement_filtered;",
        ),
        migrations.RunSQL(
            sql=ACTIVE_POINTS_SQL,
            reverse_sql="DROP VIEW IF EXISTS public.active_points;",
        ),
    ]
