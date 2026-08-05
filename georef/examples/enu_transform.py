#!/usr/bin/env python3
"""Convert between the Belvedere local ENU frame and RDN2008 / UTM 32N.

Standalone on purpose: it needs only `pyproj`, no Django and no database, so
it can be copied into a Metashape or Blender script, or run from a shell.

    # RDN2008 / UTM 32N (east north h) -> ENU
    echo "416125.449 5089423.209 2121.172" | python enu_transform.py

    # ENU -> UTM 32N
    echo "10000 10000 1000" | python enu_transform.py --inverse

    # geographic (lon lat h) instead of UTM, from arguments
    python enu_transform.py --geographic 7.917710693874493 45.95325462809565 2121.172

    # check the frame is the one this file documents
    python enu_transform.py --self-test

The project CRS is **EPSG:7791** (RDN2008 / UTM 32N, ETRF2000 epoch 2008.0),
not WGS 84. Heights are **ellipsoidal**, never orthometric. ENU Z carries the
frame's +1000 m neutral offset and is not an altitude — see
context/architecture.md.
"""

import argparse
import sys
from functools import lru_cache

import pyproj

#: The frozen frame, SRID 990001. Re-export it any time with
#: `manage.py dump_reference_frame`; `georef.tests` asserts this still matches
#: the database.
PIPELINE = (
    "+proj=pipeline "
    "+step +proj=cart +ellps=GRS80 "
    "+step +proj=topocentric +ellps=GRS80 "
    "+lat_0=45.95325462809565 +lon_0=7.917710693874493 +h_0=2121.172 "
    "+step +proj=affine +xoff=10000 +yoff=10000 +zoff=1000"
)

#: Same frame, consuming RDN2008 / UTM 32N (EPSG:7791) directly. GRS80
#: throughout — RDN2008's ellipsoid — so no step crosses a datum.
PIPELINE_FROM_UTM = PIPELINE.replace(
    "+proj=pipeline",
    "+proj=pipeline +step +inv +proj=utm +zone=32 +ellps=GRS80",
    1,
)

#: (source, ENU) pairs used by --self-test, verified against PostGIS.
KNOWN_POINTS = (
    ((416125.449, 5089423.209, 2121.172), (10000.0, 10000.0, 1000.0)),
    ((416012.633, 5089977.534, 2054.660), (9879.5912, 10553.0937, 933.4629)),
)


@lru_cache(maxsize=2)
def transformer(geographic: bool = False) -> pyproj.Transformer:
    """Transformer into the ENU frame, from geographic or from UTM 32N."""
    return pyproj.Transformer.from_pipeline(
        PIPELINE if geographic else PIPELINE_FROM_UTM
    )


def to_enu(x: float, y: float, z: float, geographic: bool = False) -> tuple:
    """(east, north, h) — or (lon, lat, h) — to (E, N, U)."""
    return transformer(geographic).transform(x, y, z)


def from_enu(e: float, n: float, u: float, geographic: bool = False) -> tuple:
    """(E, N, U) back to (east, north, h), or to (lon, lat, h)."""
    return transformer(geographic).transform(e, n, u, direction="INVERSE")


def self_test() -> int:
    """Confirm this file's pipeline still reproduces the documented values."""
    failures = 0
    for source, expected in KNOWN_POINTS:
        got = to_enu(*source)
        if max(abs(a - b) for a, b in zip(got, expected, strict=True)) > 1e-4:
            print(f"FAIL {source} -> {got}, expected {expected}", file=sys.stderr)
            failures += 1
        # and back again
        back = from_enu(*got)
        if max(abs(a - b) for a, b in zip(back, source, strict=True)) > 1e-6:
            print(f"FAIL round trip {source} -> {back}", file=sys.stderr)
            failures += 1

    print("self-test failed" if failures else "self-test passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "coordinates",
        nargs="*",
        type=float,
        help="One point as three numbers. Omit to read lines from stdin.",
    )
    parser.add_argument(
        "--inverse", action="store_true", help="ENU -> UTM 32N (or geographic)."
    )
    parser.add_argument(
        "--geographic",
        action="store_true",
        help="Use lon/lat/h instead of UTM 32N east/north/h.",
    )
    parser.add_argument("--decimals", type=int, default=4)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    convert = from_enu if args.inverse else to_enu

    if args.coordinates:
        if len(args.coordinates) != 3:
            parser.error("give exactly three numbers, or none to read stdin")
        rows = [args.coordinates]
    else:
        rows = [
            [float(value) for value in line.split()]
            for line in sys.stdin
            if line.strip() and not line.startswith("#")
        ]

    for row in rows:
        x, y, z = convert(*row, geographic=args.geographic)
        print(f"{x:.{args.decimals}f} {y:.{args.decimals}f} {z:.{args.decimals}f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
