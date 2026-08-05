"""Constants of the local ENU reference frame.

These values are baked into migrations (geometry column SRIDs, the
`spatial_ref_sys` row) and must therefore never change once applied. A
corrected frame gets a *new* SRID; see `georef.models.ReferenceFrame`.
"""

# SRID of the Belvedere local ENU frame, in the PostGIS private range.
ENU_SRID = 990001

# Allowed range for locally defined frames (matches the CHECK constraint).
LOCAL_SRID_MIN = 990000
LOCAL_SRID_MAX = 991000

# Geographic 3D CRS the transformation pipeline consumes. Keeping the pipeline
# geographic-first (instead of baking `+inv +proj=utm +zone=32` into it) means
# the frame is not tied to UTM; verified equivalent to 1.5e-8 m on real data.
GEOGRAPHIC_3D_SRID = 4979

# Source CRS of the survey data (UTM 32N / WGS84-ETRF2000).
PROJECT_SRID = 32632

# Name of the canonical frame inserted by `georef.migrations.0003`.
BELVEDERE_FRAME_NAME = "belvedere-enu"

# Semi-major axis and inverse flattening of the supported ellipsoids.
ELLIPSOIDS: dict[str, tuple[float, float]] = {
    "GRS80": (6378137.0, 298.257222101),
    "WGS84": (6378137.0, 298.257223563),
}
