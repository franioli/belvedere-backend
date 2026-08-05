"""View DDL as it stood before the `ds_*` -> `std_*` rename in `surveys/0024`.

Frozen on purpose. `surveys/sql.py` describes the *current* schema, so
migrations that run before the rename — `0022` on a fresh database, and the
reverse of `0024` — cannot use it: they would emit `meas.std_east` against a
table whose column is still `ds_east`.

Not named `0*.py`, so Django does not mistake it for a migration.
"""

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


def create_views() -> str:
    """The four views with the pre-rename `points_measurements`.

    The other three never referenced the renamed columns, so they come from
    `surveys.sql` unchanged.
    """
    from surveys.sql import (
        ACTIVE_POINTS_SQL,
        POINTS_MOVEMENT_FILTERED_SQL,
        POINTS_MOVEMENT_RAW_SQL,
    )

    return (
        POINTS_MEASUREMENTS_SQL
        + POINTS_MOVEMENT_RAW_SQL
        + POINTS_MOVEMENT_FILTERED_SQL
        + ACTIVE_POINTS_SQL
    )
