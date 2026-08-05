"""Python-side access to a reference frame, via pyproj.

PostGIS is the production path — `georef_to_enu` / `georef_from_enu` do the
work for every stored geometry. This module exists so validation and offline
consumers (Metashape / Blender exports) can reach the same frame without a
database, and so nothing here has to reimplement geodesy.

Note that pyproj bundles its own PROJ, which need not match the database's.
`georef.validation.check_matches_pyproj` exists to prove the two agree.
"""

import math
from functools import lru_cache

import pyproj

Vector3 = tuple[float, float, float]


@lru_cache(maxsize=8)
def _transformer(pipeline: str) -> pyproj.Transformer:
    return pyproj.Transformer.from_pipeline(pipeline)


def transformer_for(frame) -> pyproj.Transformer:
    """Transformer for a frame, driven by its generated pipeline."""
    return _transformer(frame.proj_pipeline)


def to_enu(frame, lon: float, lat: float, h: float) -> Vector3:
    """Geographic 3D (degrees, degrees, ellipsoidal metres) to local ENU."""
    return transformer_for(frame).transform(lon, lat, h)


def from_enu(frame, e: float, n: float, u: float) -> Vector3:
    """Local ENU back to geographic 3D, as (lon, lat, h)."""
    return transformer_for(frame).transform(e, n, u, direction="INVERSE")


@lru_cache(maxsize=8)
def _ellipsoid(ellps: str) -> tuple[float, float]:
    """Semi-major axis and first eccentricity squared, from PROJ's database."""
    ellipsoid = pyproj.CRS.from_proj4(f"+proj=latlong +ellps={ellps}").ellipsoid
    if ellipsoid is None or ellipsoid.inverse_flattening is None:
        raise ValueError(f"PROJ does not define a flattened ellipsoid {ellps!r}")
    f = 1.0 / ellipsoid.inverse_flattening
    return ellipsoid.semi_major_metre, f * (2.0 - f)


def geod_for(frame) -> pyproj.Geod:
    """Geodesic calculator on the frame's ellipsoid."""
    return pyproj.Geod(ellps=frame.ellps)


def prime_vertical_radius(lat: float, ellps: str = "GRS80") -> float:
    """Radius of curvature in the prime vertical, `N`.

    Governs how far a point's ellipsoidal height displaces it horizontally in
    a topocentric frame — the `h * d / N` term by which `+proj=ortho` differs
    from true ENU, and the `1 + h / N` stretch of a geodesic distance.
    """
    a, e2 = _ellipsoid(ellps)
    return a / math.sqrt(1.0 - e2 * math.sin(math.radians(lat)) ** 2)


def gaussian_radius(lat: float, ellps: str = "GRS80") -> float:
    """Mean radius of curvature, `sqrt(M * N)` — which reduces to `a√(1-e²)/w`.

    Predicts the tangent-plane term `d^2 / 2R` separating U from ellipsoidal
    height.
    """
    a, e2 = _ellipsoid(ellps)
    w = 1.0 - e2 * math.sin(math.radians(lat)) ** 2
    return a * math.sqrt(1.0 - e2) / w


def format_enu_point(point) -> str:
    """Render an ENU `Point` for admin display."""
    if point is None:
        return "—"
    return f"E {point.x:.3f}    N {point.y:.3f}    U {point.z:.3f}"
