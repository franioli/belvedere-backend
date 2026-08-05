"""Closed-form ENU transformations — independent reference implementation.

This exists to *cross-check* the PROJ pipeline used by the database, and to
give Python callers (Metashape / Blender exports) the frame without a database
round-trip. It deliberately does not reimplement the transverse Mercator
projection: callers feed geodetic coordinates, which PostGIS or pyproj can
produce.
"""

import math

from georef.constants import ELLIPSOIDS

Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]


def ellipsoid_constants(ellps: str = "GRS80") -> tuple[float, float]:
    """Semi-major axis `a` and first eccentricity squared `e2`."""
    try:
        a, inverse_flattening = ELLIPSOIDS[ellps]
    except KeyError:
        raise ValueError(f"Unsupported ellipsoid {ellps!r}") from None
    f = 1.0 / inverse_flattening
    return a, f * (2.0 - f)


def geodetic_to_ecef(lat: float, lon: float, h: float, ellps: str = "GRS80") -> Vector3:
    """Geodetic (degrees, degrees, ellipsoidal metres) to geocentric XYZ."""
    a, e2 = ellipsoid_constants(ellps)
    phi, lam = math.radians(lat), math.radians(lon)
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    n = a / math.sqrt(1.0 - e2 * sin_phi * sin_phi)
    return (
        (n + h) * cos_phi * math.cos(lam),
        (n + h) * cos_phi * math.sin(lam),
        (n * (1.0 - e2) + h) * sin_phi,
    )


def ecef_to_geodetic(x: float, y: float, z: float, ellps: str = "GRS80") -> Vector3:
    """Geocentric XYZ to geodetic, via Bowring's closed form.

    Non-iterative and sub-millimetre for terrestrial heights.
    """
    a, e2 = ellipsoid_constants(ellps)
    b = a * math.sqrt(1.0 - e2)
    ep2 = (a * a - b * b) / (b * b)

    p = math.hypot(x, y)
    if p == 0.0:  # on the polar axis
        return (math.copysign(90.0, z), 0.0, abs(z) - b)

    theta = math.atan2(z * a, p * b)
    phi = math.atan2(
        z + ep2 * b * math.sin(theta) ** 3,
        p - e2 * a * math.cos(theta) ** 3,
    )
    lam = math.atan2(y, x)
    n = a / math.sqrt(1.0 - e2 * math.sin(phi) ** 2)
    return (math.degrees(phi), math.degrees(lam), p / math.cos(phi) - n)


def rotation_matrix(lat_0: float, lon_0: float) -> Matrix3:
    """ECEF → ENU rotation about the origin. Orthonormal by construction."""
    phi, lam = math.radians(lat_0), math.radians(lon_0)
    sin_phi, cos_phi = math.sin(phi), math.cos(phi)
    sin_lam, cos_lam = math.sin(lam), math.cos(lam)
    return (
        (-sin_lam, cos_lam, 0.0),
        (-sin_phi * cos_lam, -sin_phi * sin_lam, cos_phi),
        (cos_phi * cos_lam, cos_phi * sin_lam, sin_phi),
    )


def enu_forward(
    lat: float,
    lon: float,
    h: float,
    *,
    lat_0: float,
    lon_0: float,
    h_0: float,
    x_off: float = 0.0,
    y_off: float = 0.0,
    z_off: float = 0.0,
    ellps: str = "GRS80",
) -> Vector3:
    """Geodetic to local ENU, false origin included."""
    x, y, z = geodetic_to_ecef(lat, lon, h, ellps)
    x0, y0, z0 = geodetic_to_ecef(lat_0, lon_0, h_0, ellps)
    dx, dy, dz = x - x0, y - y0, z - z0
    r = rotation_matrix(lat_0, lon_0)
    return (
        r[0][0] * dx + r[0][1] * dy + r[0][2] * dz + x_off,
        r[1][0] * dx + r[1][1] * dy + r[1][2] * dz + y_off,
        r[2][0] * dx + r[2][1] * dy + r[2][2] * dz + z_off,
    )


def enu_inverse(
    e: float,
    n: float,
    u: float,
    *,
    lat_0: float,
    lon_0: float,
    h_0: float,
    x_off: float = 0.0,
    y_off: float = 0.0,
    z_off: float = 0.0,
    ellps: str = "GRS80",
) -> Vector3:
    """Local ENU back to geodetic. The rotation is orthonormal, so transposed."""
    de, dn, du = e - x_off, n - y_off, u - z_off
    r = rotation_matrix(lat_0, lon_0)
    x0, y0, z0 = geodetic_to_ecef(lat_0, lon_0, h_0, ellps)
    x = r[0][0] * de + r[1][0] * dn + r[2][0] * du + x0
    y = r[0][1] * de + r[1][1] * dn + r[2][1] * du + y0
    z = r[0][2] * de + r[1][2] * dn + r[2][2] * du + z0
    return ecef_to_geodetic(x, y, z, ellps)


def prime_vertical_radius(lat: float, ellps: str = "GRS80") -> float:
    """Radius of curvature in the prime vertical, `N`.

    Governs how far a point's ellipsoidal height displaces it horizontally in
    a topocentric frame — the `h * d / N` term by which `+proj=ortho` differs
    from true ENU.
    """
    a, e2 = ellipsoid_constants(ellps)
    return a / math.sqrt(1.0 - e2 * math.sin(math.radians(lat)) ** 2)


def gaussian_radius(lat: float, ellps: str = "GRS80") -> float:
    """Mean radius of curvature at a latitude — `sqrt(M * N)`.

    Used to predict the tangent-plane vs. ellipsoidal-height difference
    `d^2 / 2R` between the true ENU frame and its orthographic display CRS.
    """
    a, e2 = ellipsoid_constants(ellps)
    w = 1.0 - e2 * math.sin(math.radians(lat)) ** 2
    meridional = a * (1.0 - e2) / w**1.5
    prime_vertical = a / math.sqrt(w)
    return math.sqrt(meridional * prime_vertical)


def format_enu_point(point) -> str:
    """Render an ENU `Point` for admin display."""
    if point is None:
        return "—"
    return f"E {point.x:.3f}    N {point.y:.3f}    U {point.z:.3f}"


def frame_kwargs(frame) -> dict[str, float | str]:
    """Keyword arguments for `enu_forward`/`enu_inverse` from a ReferenceFrame."""
    return {
        "lat_0": frame.lat_0,
        "lon_0": frame.lon_0,
        "h_0": frame.h_0,
        "x_off": frame.x_off,
        "y_off": frame.y_off,
        "z_off": frame.z_off,
        "ellps": frame.ellps,
    }
