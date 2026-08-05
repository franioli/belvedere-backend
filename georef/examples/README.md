# Transforming to and from the local ENU frame

Four ways to do the same thing: the database, the `cct` command line, a
standalone Python script, and Django. Every command and number below was run
against the live frame — the outputs are real, not illustrative.

**Heights are ellipsoidal.** ENU Z also carries the frame's `+1000 m` neutral
offset, so it is *not* an altitude. Orthometric heights live in
`measurements.h_orto` (geoid undulation ≈ 54.39 m here).

The reference point used throughout is monument **D12**, the frame origin:

| | east / lon | north / lat | h |
|---|---|---|---|
| UTM 32N (EPSG:32632) | 416125.449 | 5089423.209 | 2121.172 |
| geographic (EPSG:4979) | 7.917710693886419 | 45.95325462701091 | 2121.172 |
| **local ENU (SRID 990001)** | **10000** | **10000** | **1000** |

---

## 1. In the database — the primary path

`georef_from_enu()` is the **only** correct inverse. Do not `ST_Transform()` an
ENU geometry: the registered CRS is `+proj=ortho`, which is off by ~0.7 m
horizontally and ~0.36 m vertically. See `context/architecture.md`.

```sql
-- forward: UTM 32N -> ENU
SELECT ST_AsText(georef_to_enu(
    ST_SetSRID(ST_MakePoint(416125.449, 5089423.209, 2121.172), 32632), 990001));
--  POINT Z (10000 10000 1000)

-- inverse: ENU -> UTM 32N
SELECT ST_AsText(georef_from_enu(
    ST_SetSRID(ST_MakePoint(10000, 10500, 900), 990001), 32632));
--  POINT Z (416132.23379510903 5089922.847586099 2021.1916218176484)
```

Stored geometries are already there — `measurements.geom_enu` and
`image_index_camera.location_enu` are kept current by triggers:

```sql
SELECT p.label, ST_AsText(m.geom_enu)
FROM measurements m JOIN points p ON m.point = p.id
WHERE p.label = 'D12' LIMIT 1;
```

## 2. From the shell with `cct`

`cct` ships with PROJ. Get the pipeline straight from the database so it can
never go stale:

```bash
PIPE=$(uv run python manage.py shell -c \
  "from georef.models import ReferenceFrame; \
   print(ReferenceFrame.objects.get(srid=990001).proj_pipeline)" | tail -1)
```

or paste it (this is the frozen frame):

```bash
PIPE="+proj=pipeline +step +proj=cart +ellps=GRS80 +step +proj=topocentric +ellps=GRS80 +lat_0=45.95325462701091 +lon_0=7.917710693886419 +h_0=2121.172 +step +proj=affine +xoff=10000 +yoff=10000 +zoff=1000"
```

The pipeline consumes **geographic 3D**, `lon lat h`:

```bash
# forward: lon lat h -> E N U          (zsh needs ${=PIPE} to word-split; bash: $PIPE)
$ printf '7.917710693886419 45.95325462701091 2121.172\n' | cct -d 4 -t 0 ${=PIPE}
   10000.0000     10000.0000     1000.0000        0.0000

# inverse: E N U -> lon lat h
$ printf '10000 10000 1000\n' | cct -I -d 9 -t 0 ${=PIPE}
   7.917710694    45.953254627  2121.172000040        0.0000
```

To feed **UTM 32N** directly, prepend an inverse-UTM step. It uses `WGS84`,
the ellipsoid EPSG:32632 is actually defined on; the rest stays `GRS80`:

```bash
UTM="+proj=pipeline +step +inv +proj=utm +zone=32 +ellps=WGS84 ${PIPE#+proj=pipeline }"

# forward: east north h -> E N U
$ printf '416125.449 5089423.209 2121.172\n416012.633 5089977.534 2054.660\n' \
    | cct -d 4 -t 0 ${=UTM}
   10000.0000     10000.0000     1000.0000        0.0000
    9879.5912     10553.0937      933.4629        0.0000

# inverse: E N U -> east north h
$ printf '10000 10500 900\n' | cct -I -d 4 -t 0 ${=UTM}
  416132.2338   5089922.8476     2021.1916        0.0000

# a whole file of points
$ cct -d 4 -t 0 ${=UTM} points.txt
```

`-d` sets decimals, `-t 0` pins the time column (otherwise it prints `inf`).

## 3. Standalone Python — [`enu_transform.py`](enu_transform.py)

Needs only `pyproj`, no Django and no database, so it can be dropped into a
Metashape or Blender script.

```bash
$ printf '416125.449 5089423.209 2121.172\n' | python enu_transform.py
10000.0000 10000.0000 1000.0000

$ printf '10000 10500 900\n' | python enu_transform.py --inverse
416132.2338 5089922.8476 2021.1916

$ python enu_transform.py --geographic 7.917710693886419 45.95325462701091 2121.172
10000.0000 10000.0000 1000.0000

$ python enu_transform.py --self-test
self-test passed
```

As a library:

```python
from georef.examples.enu_transform import to_enu, from_enu

to_enu(416125.449, 5089423.209, 2121.172)          # -> (10000.0, 10000.0, 1000.0)
from_enu(10000, 10500, 900)                        # -> (416132.2338, 5089922.8476, 2021.1916)
to_enu(7.9177106939, 45.9532546270, 2121.172, geographic=True)
```

Or straight from pyproj, if you only want the three lines:

```python
import pyproj

transformer = pyproj.Transformer.from_pipeline(PIPELINE)      # geographic in
e, n, u = transformer.transform(lon, lat, h)
lon, lat, h = transformer.transform(e, n, u, direction="INVERSE")
```

## 4. Inside Django

`georef.enu` reads the frame from the database, so it always uses the live
definition:

```python
from georef.enu import from_enu, to_enu
from georef.models import ReferenceFrame

frame = ReferenceFrame.objects.get(srid=990001)
to_enu(frame, 7.917710693886419, 45.95325462701091, 2121.172)   # (10000.0, 10000.0, 1000.0)
from_enu(frame, 10000, 10000, 1000)                             # back to lon/lat/h
```

Note these take **geographic** input, matching the pipeline. For UTM, let
PostGIS do it (§1) or use the standalone script (§3).

---

## Three PROJ builds, one answer

The stack carries three separate PROJ installations. They agree exactly, which
`manage.py validate_reference_frame` checks continuously (`matches pyproj`):

| | PROJ | `416012.633 5089977.534 2054.660` → ENU |
|---|---|---|
| `cct` (system) | 9.4.0 | `9879.5912 10553.0937 933.4629` |
| PostGIS | 9.6.0 | `9879.591225758662 10553.093729395534 933.4628556942157` |
| pyproj | 9.5.1 | `9879.5912 10553.0937 933.4629` |
