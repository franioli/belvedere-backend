"""Checks a reference frame must pass before it is frozen.

Shared by `georef.tests` and the `validate_reference_frame` /
`freeze_reference_frame` management commands, so the suite that gates the
freeze is exactly the suite the tests run.

Sample points come from a `generate_series` grid built in SQL rather than
shipped as thousands of bind parameters, so each check reads as ordinary SQL.
"""

import math
from dataclasses import dataclass

import pyproj
from django.db import connection

from georef.constants import ENU_SRID, GEOGRAPHIC_3D_SRID, PROJECT_SRID
from georef.crs import crs_definition
from georef.enu import gaussian_radius, geod_for, prime_vertical_radius, to_enu
from georef.models import ReferenceFrame
from georef.sql import SPATIAL_REF_SYS_SELECT

#: Bounding box of the survey area in the project CRS, padded around the data
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


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def proj_versions() -> tuple[str, str]:
    """PROJ as seen by PostGIS and by pyproj — they need not be the same."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT postgis_proj_version()")
        # postgis_proj_version() appends NETWORK_ENABLED, paths and so on
        return cursor.fetchone()[0].split()[0], pyproj.proj_version_str


def sample_grid_cte(steps: int = 12, levels: int = 7) -> str:
    """A `steps^2 * levels` grid of source points, as a CTE named `pts`.

    Exposes `src` (a PointZ in the project CRS) and `h`.
    """
    (e0, e1), (n0, n1), (h0, h1) = (
        SAMPLE_BOUNDS["east"],
        SAMPLE_BOUNDS["north"],
        SAMPLE_BOUNDS["h"],
    )
    return f"""
    pts AS (
        SELECT ST_SetSRID(ST_MakePoint(east, north, h), {PROJECT_SRID}) AS src, h
        FROM (
            -- Postgres types bare decimal literals as `numeric`; the casts keep
            -- these floats rather than Decimals on the Python side.
            SELECT ({e0} + ({e1} - {e0}) * i / {steps - 1}.0)::double precision AS east,
                   ({n0} + ({n1} - {n0}) * j / {steps - 1}.0)::double precision AS north,
                   ({h0} + ({h1} - {h0}) * k / {levels - 1}.0)::double precision AS h
            FROM generate_series(0, {steps - 1}) AS i,
                 generate_series(0, {steps - 1}) AS j,
                 generate_series(0, {levels - 1}) AS k
        ) g
    )
    """


def _grid_size(steps: int = 12, levels: int = 7) -> int:
    return steps * steps * levels


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


def check_axis_convention(frame: ReferenceFrame) -> CheckResult:
    """E is east, N is north, U is up — and they are not swapped.

    The invariant checks cannot see this. With `x_off == y_off`, an E/N swap
    inside PROJ would satisfy round trip, rigid motion, origin identity and
    positivity alike. So probe explicitly: walk a known geodesic distance from
    the origin at a known azimuth and assert where it lands.

    A probe `s` metres away on the ellipsoid lands at `s * (1 + h/N)` in the
    frame, because the point sits `h` above the ellipsoid, and `s^2 / 2R` below
    the tangent plane.
    """
    geod = geod_for(frame)
    distance = 1000.0
    normal_radius = prime_vertical_radius(frame.lat_0, frame.ellps)
    curvature_radius = gaussian_radius(frame.lat_0, frame.ellps)

    expected_horizontal = distance * (1.0 + frame.h_0 / normal_radius)
    expected_drop = distance * distance / (2.0 * curvature_radius)

    probes = []
    for label, azimuth in (("north", 0.0), ("east", 90.0)):
        lon, lat, _ = geod.fwd(frame.lon_0, frame.lat_0, azimuth, distance)
        probes.append((label, lon, lat, frame.h_0))
    probes.append(("up", frame.lon_0, frame.lat_0, frame.h_0 + 100.0))

    failures = []
    with connection.cursor() as cursor:
        for label, lon, lat, h in probes:
            cursor.execute(
                """
                SELECT ST_X(p), ST_Y(p), ST_Z(p) FROM (
                    SELECT georef_to_enu(
                        ST_SetSRID(ST_MakePoint(%s, %s, %s), %s), %s
                    ) AS p
                ) t
                """,
                [lon, lat, h, GEOGRAPHIC_3D_SRID, frame.srid],
            )
            e, n, u = cursor.fetchone()
            de, dn, du = e - frame.x_off, n - frame.y_off, u - frame.z_off

            if label == "north":
                expected = (0.0, expected_horizontal, -expected_drop)
            elif label == "east":
                expected = (expected_horizontal, 0.0, -expected_drop)
            else:
                expected = (0.0, 0.0, 100.0)

            # cross-axis components must vanish; along-axis must match the model
            for axis, got, want in zip("ENU", (de, dn, du), expected, strict=True):
                tolerance = 1e-3 if want == 0.0 else 0.01
                if abs(got - want) > tolerance:
                    failures.append(
                        f"{label} probe {axis}: {got:+.4f} vs {want:+.4f} expected"
                    )

    return CheckResult(
        "axis convention",
        not failures,
        "; ".join(failures)
        if failures
        else f"N/E probes at {distance:.0f} m land at "
        f"{expected_horizontal:.3f} m, drop {expected_drop * 1000:.1f} mm; up probe exact",
    )


def check_round_trip(frame: ReferenceFrame) -> CheckResult:
    """`from_enu(to_enu(p))` must return the input."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH {sample_grid_cte()}
            SELECT max(ST_3DDistance(
                src, georef_from_enu(georef_to_enu(src, %s), %s)
            )) FROM pts
            """,
            [frame.srid, PROJECT_SRID],
        )
        worst = cursor.fetchone()[0]

    return CheckResult(
        "round trip",
        worst is not None and worst < TOLERANCE_M,
        f"worst of {_grid_size()} points: {worst * 1000:.6f} mm",
    )


def check_matches_pyproj(frame: ReferenceFrame) -> CheckResult:
    """PostGIS and pyproj must agree — they carry separate PROJ builds.

    This is where a version divergence between the database's PROJ and the one
    bundled in the pyproj wheel would surface.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH {sample_grid_cte()}
            SELECT ST_X(geo), ST_Y(geo), ST_Z(geo), ST_X(enu), ST_Y(enu), ST_Z(enu)
            FROM (
                SELECT ST_Transform(src, %s) AS geo, georef_to_enu(src, %s) AS enu
                FROM pts
            ) t
            """,
            [GEOGRAPHIC_3D_SRID, frame.srid],
        )
        worst = 0.0
        count = 0
        for lon, lat, h, e, n, u in cursor.fetchall():
            worst = max(worst, math.dist((e, n, u), to_enu(frame, lon, lat, h)))
            count += 1

    postgis_proj, pyproj_proj = proj_versions()
    return CheckResult(
        "matches pyproj",
        worst < TOLERANCE_M,
        f"worst of {count} points: {worst * 1000:.6f} mm "
        f"(PostGIS PROJ {postgis_proj}, pyproj PROJ {pyproj_proj})",
    )


def check_rigid_motion(frame: ReferenceFrame) -> CheckResult:
    """ENU must preserve 3D distances exactly — it is a rotation plus a shift.

    This is the check that catches a leaked UTM scale factor: it would show up
    as a systematic -0.64 mm/m, i.e. ~1.5 m over the glacier. Preserving all
    pairwise distances also means the transform is orthonormal.
    """
    cart_pipeline = f"+proj=pipeline +step +proj=cart +ellps={frame.ellps}"
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH {sample_grid_cte(steps=4, levels=3)}, projected AS (
                SELECT row_number() OVER () AS rn,
                       georef_to_enu(src, %s) AS enu,
                       ST_TransformPipeline(ST_Transform(src, %s), %s, 0) AS ecef
                FROM pts
            )
            SELECT count(*), max(abs(
                ST_3DDistance(a.enu, b.enu) - ST_3DDistance(a.ecef, b.ecef)
            ))
            FROM projected a JOIN projected b ON a.rn < b.rn
            """,
            [frame.srid, GEOGRAPHIC_3D_SRID, cart_pipeline],
        )
        pairs, worst = cursor.fetchone()

    return CheckResult(
        "rigid motion (scale)",
        worst is not None and worst < 1e-6,
        f"worst over {pairs} point pairs: {worst:.3e} m",
    )


def check_positivity(frame: ReferenceFrame) -> CheckResult:
    """The false origin must be large enough that no coordinate goes negative.

    E and N always: that is what `x_off`/`y_off` are for. U only when the frame
    declares a `z_off` — with `z_off = 0`, U is signed height above the tangent
    plane and negative values below the origin are correct.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH {sample_grid_cte()}
            SELECT min(ST_X(p)), max(ST_X(p)),
                   min(ST_Y(p)), max(ST_Y(p)),
                   min(ST_Z(p)), max(ST_Z(p))
            FROM (SELECT georef_to_enu(src, %s) AS p FROM pts) t
            """,
            [frame.srid],
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


def check_ortho_display_crs(frame: ReferenceFrame) -> CheckResult:
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
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH {sample_grid_cte(steps=5, levels=3)}
            SELECT ST_X(enu), ST_Y(enu), ST_Z(enu),
                   ST_X(ortho), ST_Y(ortho), ST_Z(ortho), h
            FROM (
                SELECT georef_to_enu(src, %s) AS enu,
                       ST_Transform(src, %s) AS ortho,
                       h
                FROM pts
            ) t
            """,
            [frame.srid, frame.srid],
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


def check_pipeline_route_equivalence(frame: ReferenceFrame) -> CheckResult:
    """Geographic-first pipeline vs. one that inverts UTM itself.

    Guards the decision to keep the frame independent of UTM: the `to_enu`
    route goes through `ST_Transform(..., 6705)`, which for EPSG:7791 is a pure
    inverse projection — same datum, same ellipsoid, no shift.

    Both routes use GRS80, the ellipsoid RDN2008 is defined on, so this now
    agrees to ~1e-9 m. Under the old EPSG:32632 label it could only reach
    0.12 mm, because the inverse-UTM step had to use WGS84 and the two
    ellipsoids differ.
    """
    utm_pipeline = frame.proj_pipeline.replace(
        "+proj=pipeline",
        f"+proj=pipeline +step +inv +proj=utm +zone=32 +ellps={frame.ellps}",
        1,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH {sample_grid_cte(steps=5, levels=3)}
            SELECT count(*), max(ST_3DDistance(
                georef_to_enu(src, %s),
                ST_TransformPipeline(src, %s, %s)
            )) FROM pts
            """,
            [frame.srid, utm_pipeline, frame.srid],
        )
        count, worst = cursor.fetchone()

    return CheckResult(
        "pipeline route equivalence",
        worst is not None and worst < TOLERANCE_M,
        f"worst of {count} points: {worst * 1000:.6f} mm",
    )


def check_materialised_up_to_date(frame: ReferenceFrame) -> CheckResult:
    """Stored ENU geometries must match what the frame produces now.

    Nothing else notices when they diverge: every other check derives
    coordinates fresh. Editing the frame in the admin regenerates
    `proj_pipeline` (a generated column) but leaves stored geometries stale,
    and so does a `recompute_enu` that half-finished.
    """
    statements = (
        (
            "measurements",
            """
            SELECT count(*) FILTER (WHERE geom_enu IS NULL),
                   count(*) FILTER (WHERE geom_enu IS NOT NULL),
                   coalesce(max(ST_3DDistance(geom_enu, georef_to_enu(
                       ST_SetSRID(ST_MakePoint(east, north, h), %s), %s))), 0)
            FROM measurements
            WHERE east IS NOT NULL AND north IS NOT NULL AND h IS NOT NULL
            """,
            True,
        ),
        (
            "cameras",
            """
            SELECT count(*) FILTER (WHERE location_enu IS NULL),
                   count(*) FILTER (WHERE location_enu IS NOT NULL),
                   coalesce(max(ST_3DDistance(
                       location_enu, georef_to_enu(location, %s))), 0)
            FROM image_index_camera
            WHERE location IS NOT NULL
            """,
            False,
        ),
    )

    parts = []
    worst = 0.0
    missing_total = 0
    with connection.cursor() as cursor:
        for label, sql, needs_project_srid in statements:
            params = [PROJECT_SRID, frame.srid] if needs_project_srid else [frame.srid]
            cursor.execute(sql, params)
            missing, present, drift = cursor.fetchone()
            worst = max(worst, drift)
            missing_total += missing
            parts.append(f"{present} {label} (missing {missing})")

    return CheckResult(
        "materialised up to date",
        worst < TOLERANCE_M and missing_total == 0,
        f"{', '.join(parts)}, worst drift {worst * 1000:.6f} mm",
    )


def check_crs_definition_current(frame: ReferenceFrame) -> CheckResult:
    """`spatial_ref_sys` must match what `georef.crs` generates today."""
    with connection.cursor() as cursor:
        cursor.execute(SPATIAL_REF_SYS_SELECT, [frame.srid])
        row = cursor.fetchone()

    if row is None:
        return CheckResult(
            "CRS definition current", False, f"no spatial_ref_sys row for {frame.srid}"
        )

    expected_proj4, expected_srtext = crs_definition(frame)
    stale = [
        name
        for name, stored, expected in (
            ("proj4text", row[0], expected_proj4),
            ("srtext", row[1], expected_srtext),
        )
        if stored != expected
    ]

    return CheckResult(
        "CRS definition current",
        not stale,
        f"{', '.join(stale)} stale — re-run the CRS migration"
        if stale
        else "proj4text and srtext match the generator",
    )


def run_checks(srid: int = ENU_SRID) -> list[CheckResult]:
    """Run every frame check. Order is stable so output can be diffed."""
    frame = ReferenceFrame.objects.get(srid=srid)
    return [
        check_pipeline_generated(frame),
        check_origin_identity(frame),
        check_origin_mark_agreement(frame),
        check_axis_convention(frame),
        check_round_trip(frame),
        check_matches_pyproj(frame),
        check_rigid_motion(frame),
        check_positivity(frame),
        check_ortho_display_crs(frame),
        check_pipeline_route_equivalence(frame),
        check_materialised_up_to_date(frame),
        check_crs_definition_current(frame),
    ]
