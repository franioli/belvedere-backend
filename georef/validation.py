"""Checks a reference frame must pass before it is frozen.

Shared by `georef.tests` and the `validate_reference_frame` /
`freeze_reference_frame` management commands, so the suite that gates the
freeze is exactly the suite the tests run.
"""

import math
from dataclasses import dataclass

from django.db import connection

from georef.constants import ENU_SRID, GEOGRAPHIC_3D_SRID, PROJECT_SRID
from georef.enu import (
    enu_forward,
    frame_kwargs,
    gaussian_radius,
    prime_vertical_radius,
    rotation_matrix,
)
from georef.models import ReferenceFrame

#: Bounding box of the survey area in EPSG:32632, padded around the real data
#: extent (E 415327–416659, N 5087986–5091322, h 1832–2292).
SAMPLE_BOUNDS = {
    "east": (415300.0, 416700.0),
    "north": (5087900.0, 5091400.0),
    "h": (1800.0, 2300.0),
}

#: Everything geodetic must agree to a tenth of a millimetre.
TOLERANCE_M = 1e-4

#: Repeat measurements of the origin monument scatter at the centimetre level
#: (D12: sd 4/9/26 mm over 2015-2026), so agreement with the frozen origin is
#: judged against survey noise, not against the geodetic tolerance.
ORIGIN_MARK_TOLERANCE_M = 0.10

Sample = tuple[float, float, float]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def sample_grid(steps: int = 12, levels: int = 7) -> list[Sample]:
    """Deterministic grid of `steps^2 * levels` points spanning the survey area."""

    def axis(lo: float, hi: float, n: int) -> list[float]:
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    return [
        (east, north, h)
        for east in axis(*SAMPLE_BOUNDS["east"], steps)
        for north in axis(*SAMPLE_BOUNDS["north"], steps)
        for h in axis(*SAMPLE_BOUNDS["h"], levels)
    ]


def _values_clause(samples: list[Sample]) -> tuple[str, list[float]]:
    rows = ", ".join(["(%s, %s, %s)"] * len(samples))
    params: list[float] = [value for sample in samples for value in sample]
    return rows, params


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_pipeline_generated(frame: ReferenceFrame) -> CheckResult:
    pipeline = frame.proj_pipeline or ""
    ok = pipeline.startswith("+proj=pipeline") and "+proj=topocentric" in pipeline
    return CheckResult(
        "pipeline generated",
        ok,
        pipeline if ok else f"unexpected pipeline: {pipeline!r}",
    )


def check_origin_identity(frame: ReferenceFrame) -> CheckResult:
    """The frame's own origin must transform to the false origin exactly.

    A pure self-consistency invariant: nothing measured enters this, so any
    discrepancy means the pipeline disagrees with the stored parameters.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ST_X(p), ST_Y(p), ST_Z(p) FROM (
                SELECT georef_to_enu(
                    ST_SetSRID(ST_MakePoint(%s, %s, %s), %s), %s
                ) AS p
            ) t
            """,
            [frame.lon_0, frame.lat_0, frame.h_0, GEOGRAPHIC_3D_SRID, frame.srid],
        )
        row = cursor.fetchone()

    offset = math.dist(row, (frame.x_off, frame.y_off, frame.z_off))
    return CheckResult(
        "origin identity",
        offset < TOLERANCE_M,
        f"origin maps to ({row[0]:.6f}, {row[1]:.6f}, {row[2]:.6f}), "
        f"off by {offset * 1000:.6f} mm",
    )


def check_origin_mark_agreement(frame: ReferenceFrame) -> CheckResult:
    """The physical monument must sit on the false origin, within survey noise.

    Distinct from `check_origin_identity`: this one compares *measurements* of
    the mark against the frozen origin, so it can never be exact — the origin
    is one chosen coordinate and every campaign re-measures the monument. It
    catches a frame built on the wrong mark or a transcription error, not
    sub-millimetre disagreement. Passes trivially where there is no data.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*), max(ST_3DDistance(
                georef_to_enu(ST_SetSRID(ST_MakePoint(m.east, m.north, m.h), %s), %s),
                ST_SetSRID(ST_MakePoint(%s, %s, %s), %s)
            ))
            FROM measurements m
            JOIN points pt ON m.point = pt.id
            WHERE pt.label = %s
            """,
            [
                PROJECT_SRID,
                frame.srid,
                frame.x_off,
                frame.y_off,
                frame.z_off,
                frame.srid,
                frame.origin_mark,
            ],
        )
        count, worst = cursor.fetchone()

    if not count:
        return CheckResult(
            "origin mark agreement",
            True,
            f"no measurements of {frame.origin_mark} in this database",
        )

    return CheckResult(
        "origin mark agreement",
        worst < ORIGIN_MARK_TOLERANCE_M,
        f"{count} measurement(s) of {frame.origin_mark}, worst "
        f"{worst * 1000:.1f} mm from the false origin",
    )


def check_round_trip(frame: ReferenceFrame, samples: list[Sample]) -> CheckResult:
    """`from_enu(to_enu(p))` must return the input."""
    rows, params = _values_clause(samples)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT max(ST_3DDistance(src, georef_from_enu(georef_to_enu(src, %s), %s)))
            FROM (
                SELECT ST_SetSRID(ST_MakePoint(e, n, h), %s) AS src
                FROM (VALUES {rows}) AS v(e, n, h)
            ) t
            """,
            [frame.srid, PROJECT_SRID, PROJECT_SRID, *params],
        )
        worst = cursor.fetchone()[0]

    return CheckResult(
        "round trip",
        worst is not None and worst < TOLERANCE_M,
        f"worst of {len(samples)} points: {worst * 1000:.6f} mm",
    )


def check_against_closed_form(
    frame: ReferenceFrame, samples: list[Sample]
) -> CheckResult:
    """PROJ's topocentric implementation vs. the independent Python one."""
    rows, params = _values_clause(samples)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT ST_X(geo), ST_Y(geo), ST_Z(geo),
                   ST_X(enu), ST_Y(enu), ST_Z(enu)
            FROM (
                SELECT ST_Transform(src, %s) AS geo, georef_to_enu(src, %s) AS enu
                FROM (
                    SELECT ST_SetSRID(ST_MakePoint(e, n, h), %s) AS src
                    FROM (VALUES {rows}) AS v(e, n, h)
                ) s
            ) t
            """,
            [GEOGRAPHIC_3D_SRID, frame.srid, PROJECT_SRID, *params],
        )
        worst = 0.0
        for lon, lat, h, e, n, u in cursor.fetchall():
            expected = enu_forward(lat, lon, h, **frame_kwargs(frame))
            worst = max(worst, math.dist((e, n, u), expected))

    return CheckResult(
        "PROJ vs closed form",
        worst < TOLERANCE_M,
        f"worst of {len(samples)} points: {worst * 1000:.6f} mm",
    )


def check_rigid_motion(frame: ReferenceFrame, samples: list[Sample]) -> CheckResult:
    """ENU must preserve 3D distances exactly — it is a rotation plus a shift.

    This is the check that catches a leaked UTM scale factor: it would show up
    as a systematic -0.64 mm/m, i.e. ~1.5 m over the glacier.
    """
    subset = samples[:: max(1, len(samples) // 40)]
    rows, params = _values_clause(subset)
    cart_pipeline = f"+proj=pipeline +step +proj=cart +ellps={frame.ellps}"

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH pts AS (
                SELECT ST_SetSRID(ST_MakePoint(e, n, h), %s) AS src
                FROM (VALUES {rows}) AS v(e, n, h)
            ), projected AS (
                SELECT
                    row_number() OVER () AS rn,
                    georef_to_enu(src, %s) AS enu,
                    ST_TransformPipeline(ST_Transform(src, %s), %s, 0) AS ecef
                FROM pts
            )
            SELECT max(abs(ST_3DDistance(a.enu, b.enu) - ST_3DDistance(a.ecef, b.ecef)))
            FROM projected a JOIN projected b ON a.rn < b.rn
            """,
            [
                PROJECT_SRID,
                *params,
                frame.srid,
                GEOGRAPHIC_3D_SRID,
                cart_pipeline,
            ],
        )
        worst = cursor.fetchone()[0]

    return CheckResult(
        "rigid motion (scale)",
        worst is not None and worst < 1e-6,
        f"worst distance error over {len(subset)} points: {worst:.3e} m",
    )


def check_orthonormality(frame: ReferenceFrame) -> CheckResult:
    """`R^T R = I` for the ECEF->ENU rotation."""
    r = rotation_matrix(frame.lat_0, frame.lon_0)
    worst = 0.0
    for i in range(3):
        for j in range(3):
            dot = sum(r[k][i] * r[k][j] for k in range(3))
            worst = max(worst, abs(dot - (1.0 if i == j else 0.0)))
    return CheckResult(
        "orthonormality", worst < 1e-12, f"max |R^T R - I| = {worst:.3e}"
    )


def check_positivity(frame: ReferenceFrame, samples: list[Sample]) -> CheckResult:
    """The false origin must be large enough that no coordinate goes negative.

    E and N always: that is what `x_off`/`y_off` are for. U only when the frame
    declares a `z_off` — with `z_off = 0`, U is signed height above the tangent
    plane and negative values below the origin are correct.
    """
    rows, params = _values_clause(samples)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT min(ST_X(p)), max(ST_X(p)),
                   min(ST_Y(p)), max(ST_Y(p)),
                   min(ST_Z(p)), max(ST_Z(p))
            FROM (
                SELECT georef_to_enu(ST_SetSRID(ST_MakePoint(e, n, h), %s), %s) AS p
                FROM (VALUES {rows}) AS v(e, n, h)
            ) t
            """,
            [PROJECT_SRID, frame.srid, *params],
        )
        min_e, max_e, min_n, max_n, min_u, max_u = cursor.fetchone()

    ok = min_e > 0 and min_n > 0
    if frame.z_off:
        ok = ok and min_u > 0

    return CheckResult(
        "positivity",
        ok,
        f"E {min_e:.1f}..{max_e:.1f}, N {min_n:.1f}..{max_n:.1f}, "
        f"U {min_u:.1f}..{max_u:.1f}" + ("" if frame.z_off else " (signed, z_off = 0)"),
    )


def check_ortho_display_crs(
    frame: ReferenceFrame, samples: list[Sample]
) -> CheckResult:
    """Characterise how the `spatial_ref_sys` ortho CRS differs from the frame.

    The ortho definition registered for QGIS is **not** interchangeable with
    the true topocentric frame, and this check pins down exactly how it
    differs, so the discrepancy stays a known quantity rather than a surprise:

    * horizontal — `+proj=ortho` projects geodetic (lat, lon) and ignores h,
      while topocentric E/N grow with the point's distance from the geocentre.
      The difference is **h * d / N**, up to ~0.7 m here. (An earlier design
      note claimed sub-millimetre; that only holds for points *on* the
      ellipsoid and misses the 2 km of altitude.)
    * vertical — ortho passes ellipsoidal h straight through, while U is
      height above the tangent plane. The difference is `d^2 / 2R`.

    Both are the reason ENU layers must never be reprojected in QGIS: keep the
    project CRS at the frame's SRID, and use `georef_from_enu()` to invert.
    """
    subset = samples[:: max(1, len(samples) // 60)]
    rows, params = _values_clause(subset)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT ST_X(enu), ST_Y(enu), ST_Z(enu),
                   ST_X(ortho), ST_Y(ortho), ST_Z(ortho), h
            FROM (
                SELECT georef_to_enu(src, %s) AS enu,
                       ST_Transform(src, %s) AS ortho,
                       h
                FROM (
                    -- Postgres types bare VALUES literals as numeric; the cast
                    -- keeps `h` a float on the Python side.
                    SELECT ST_SetSRID(ST_MakePoint(e, n, h), %s) AS src,
                           h::double precision AS h
                    FROM (VALUES {rows}) AS v(e, n, h)
                ) s
            ) t
            """,
            [frame.srid, frame.srid, PROJECT_SRID, *params],
        )
        curvature_radius = gaussian_radius(frame.lat_0, frame.ellps)
        normal_radius = prime_vertical_radius(frame.lat_0, frame.ellps)
        max_horizontal = max_vertical = 0.0
        worst_horizontal_residual = worst_vertical_residual = 0.0

        for e, n, u, ox, oy, oz, h in cursor.fetchall():
            d = math.hypot(e - frame.x_off, n - frame.y_off)

            horizontal = math.dist((e, n), (ox, oy))
            max_horizontal = max(max_horizontal, horizontal)
            worst_horizontal_residual = max(
                worst_horizontal_residual, abs(horizontal - h * d / normal_radius)
            )

            vertical = (oz - frame.h_0 + frame.z_off) - u
            max_vertical = max(max_vertical, abs(vertical))
            worst_vertical_residual = max(
                worst_vertical_residual,
                abs(vertical - d * d / (2 * curvature_radius)),
            )

    # Both differences must follow their models to 1%, with a 1 mm floor so
    # points near the origin (where both terms vanish) do not dominate.
    ok = worst_horizontal_residual < max(
        0.01 * max_horizontal, 1e-3
    ) and worst_vertical_residual < max(0.01 * max_vertical, 1e-3)

    return CheckResult(
        "ortho display CRS",
        ok,
        f"horizontal up to {max_horizontal:.3f} m, matches h*d/N to "
        f"{worst_horizontal_residual * 1000:.1f} mm; "
        f"vertical up to {max_vertical:.3f} m, matches d^2/2R to "
        f"{worst_vertical_residual * 1000:.1f} mm",
    )


def check_pipeline_route_equivalence(
    frame: ReferenceFrame, samples: list[Sample]
) -> CheckResult:
    """Geographic-first pipeline vs. one that inverts UTM itself.

    Guards the decision to keep the frame independent of UTM: the `to_enu`
    route goes through `ST_Transform(..., 4979)`, which for EPSG:32632 is a
    pure inverse projection with no datum shift.

    The inverse-UTM step must use WGS84, the ellipsoid EPSG:32632 is actually
    defined on. Using the frame's GRS80 here instead measures the GRS80/WGS84
    ellipsoid difference (~0.12 mm) rather than the thing under test.
    """
    subset = samples[:: max(1, len(samples) // 60)]
    rows, params = _values_clause(subset)
    utm_pipeline = frame.proj_pipeline.replace(
        "+proj=pipeline",
        "+proj=pipeline +step +inv +proj=utm +zone=32 +ellps=WGS84",
        1,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT max(ST_3DDistance(
                georef_to_enu(src, %s),
                ST_TransformPipeline(src, %s, %s)
            ))
            FROM (
                SELECT ST_SetSRID(ST_MakePoint(e, n, h), %s) AS src
                FROM (VALUES {rows}) AS v(e, n, h)
            ) t
            """,
            [frame.srid, utm_pipeline, frame.srid, PROJECT_SRID, *params],
        )
        worst = cursor.fetchone()[0]

    return CheckResult(
        "pipeline route equivalence",
        worst is not None and worst < TOLERANCE_M,
        f"worst of {len(subset)} points: {worst * 1000:.6f} mm",
    )


def run_checks(srid: int = ENU_SRID) -> list[CheckResult]:
    """Run every frame check. Order is stable so output can be diffed."""
    frame = ReferenceFrame.objects.get(srid=srid)
    samples = sample_grid()
    return [
        check_pipeline_generated(frame),
        check_origin_identity(frame),
        check_origin_mark_agreement(frame),
        check_round_trip(frame, samples),
        check_against_closed_form(frame, samples),
        check_rigid_motion(frame, samples),
        check_orthonormality(frame),
        check_positivity(frame, samples),
        check_ortho_display_crs(frame, samples),
        check_pipeline_route_equivalence(frame, samples),
    ]
