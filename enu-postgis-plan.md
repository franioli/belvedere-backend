# Local ENU reference frame in PostGIS — implementation plan

Add a glacier-local, orthonormal, positive-coordinate reference frame to the GNSS database, with bidirectional transformation from UTM 32N / ETRF2000, and direct visualization in QGIS.

---

## 1. Design decisions

### 1.1 How to store the transformation — structured parameters, not strings

Three candidate storage formats:

| format | pro | con |
|---|---|---|
| PROJ pipeline string | directly executable | opaque, unqueryable, easy to typo, no provenance |
| WKT2 CRS | standard, GDAL/QGIS-native | verbose; topocentric CRS support varies by PROJ version |
| **structured parameters** | queryable, auditable, versionable, single source of truth | must generate the strings |

**Decision: structured parameters are canonical; pipeline and WKT2 are *derived* columns**, regenerated from the parameters. This prevents the classic failure where someone edits a string and the numbers silently diverge from the documented origin.

A frame definition is immutable once used. Corrections create a **new row with a new SRID**, never an UPDATE — otherwise every historical coordinate silently changes meaning.

### 1.2 Frame definition

Topocentric ENU about an origin at a physical GNSS monument, plus a false origin so all coordinates are positive:

```
UTM32N/ETRF2000 → geographic → ECEF → topocentric ENU(φ₀,λ₀,h₀) → +(xoff, yoff, zoff)
```

- Origin = a long-term GNSS reference mark (re-occupiable, ties historical campaigns).
- `h₀` **ellipsoidal** (confirmed: geoid applied only to final DEM products).
- `xoff = yoff = 10000` → glacier lands in 7000–13000 m, positive, 5 digits, visually unmistakable vs UTM.
- `zoff` chosen so U ≥ 0 over the area of interest, or 0 if signed height is acceptable.

### 1.3 Datum epoch — resolve before freezing

The real risk is not the projection math, it is mixing realizations across years:

- ETRF2000 (epoch 2008.0, EPSG:7796 3D / 6706) is plate-fixed → no drift.
- ITRF/WGS84 drifts ~2.5 cm/yr at 46°N → ~45 cm since 2008.
- Campaigns processed with PPP or foreign CORS may be in ITRF; Italian NRTK output is ETRF2000.

A systematic inter-annual offset here will masquerade as glacier motion. Audit each campaign's realization first; store it per observation (§2.1) so this stays visible forever.

### 1.4 Implementation strategy — two layers

1. **`ST_TransformPipeline`** (PostGIS ≥ 3.4, PROJ ≥ 8) — primary path, uses PROJ's own topocentric implementation.
2. **Pure-SQL closed-form ENU** — reference implementation used by the test suite to validate (1), and a fallback if the PROJ version lacks `+proj=topocentric`.

Both must agree to < 0.1 mm. Implementing both is cheap and catches PROJ version surprises immediately.

---

## 2. Schema

### 2.1 Frame definition table

```sql
CREATE TABLE ref_frame (
    srid            integer PRIMARY KEY
                    CHECK (srid BETWEEN 990000 AND 991000),   -- private range
    name            text        NOT NULL UNIQUE,
    description     text,

    -- origin (canonical parameters)
    origin_mark     text        NOT NULL,          -- GNSS monument label
    lat_0           double precision NOT NULL,     -- deg, 7+ decimals
    lon_0           double precision NOT NULL,
    h_0             double precision NOT NULL,     -- ELLIPSOIDAL metres
    ellps           text        NOT NULL DEFAULT 'GRS80',

    -- false origin
    x_off           double precision NOT NULL DEFAULT 0,
    y_off           double precision NOT NULL DEFAULT 0,
    z_off           double precision NOT NULL DEFAULT 0,

    -- provenance
    base_srid       integer     NOT NULL,          -- source CRS of lat_0/lon_0/h_0
    datum_epoch     numeric(7,2),                  -- e.g. 2008.00
    valid_from      date        NOT NULL DEFAULT CURRENT_DATE,
    frozen          boolean     NOT NULL DEFAULT false,
    notes           text,

    -- derived (regenerated, never hand-edited)
    proj_pipeline   text,
    wkt2            text
);
```

Immutability guard:

```sql
CREATE FUNCTION ref_frame_freeze() RETURNS trigger AS $$
BEGIN
    IF OLD.frozen AND (
        NEW.lat_0 IS DISTINCT FROM OLD.lat_0 OR
        NEW.lon_0 IS DISTINCT FROM OLD.lon_0 OR
        NEW.h_0   IS DISTINCT FROM OLD.h_0   OR
        NEW.x_off IS DISTINCT FROM OLD.x_off OR
        NEW.y_off IS DISTINCT FROM OLD.y_off OR
        NEW.z_off IS DISTINCT FROM OLD.z_off
    ) THEN
        RAISE EXCEPTION 'frame % is frozen; define a new SRID instead', OLD.srid;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
```

### 2.2 Observation metadata

Add to the GNSS measurements table (or a joined campaign table):

```sql
ALTER TABLE gnss_obs
    ADD COLUMN source_srid   integer,      -- as-measured CRS
    ADD COLUMN datum_realization text,     -- 'ETRF2000', 'ITRF2014', 'IGS20', ...
    ADD COLUMN obs_epoch     numeric(9,4), -- decimal year
    ADD COLUMN height_type   text CHECK (height_type IN ('ellipsoidal','orthometric'));
```

`height_type` should be `'ellipsoidal'` everywhere; the constraint makes any future exception loud rather than silent.

---

## 3. Pipeline generation

```sql
CREATE FUNCTION enu_pipeline(f ref_frame) RETURNS text AS $$
    SELECT format(
        '+proj=pipeline '
        '+step +proj=cart +ellps=%s '
        '+step +proj=topocentric +ellps=%s +lat_0=%s +lon_0=%s +h_0=%s '
        '+step +proj=affine +xoff=%s +yoff=%s +zoff=%s',
        f.ellps, f.ellps,
        f.lat_0::text, f.lon_0::text, f.h_0::text,
        f.x_off::text, f.y_off::text, f.z_off::text
    );
$$ LANGUAGE sql IMMUTABLE;
```

**Input must be geographic 3D** (lon, lat, h). `+proj=cart` consumes degrees/metres; feeding it projected UTM is exactly the "Mismatched units between step 1 and 2" error. If the source is UTM, prepend:

```
+step +inv +proj=utm +zone=32 +ellps=GRS80
```

Cleanest: normalize everything to EPSG:7796 (ETRF2000 geographic 3D) on ingest, so the pipeline always starts from geographic.

---

## 4. Transformation functions

### 4.1 Primary — PROJ

```sql
CREATE FUNCTION to_enu(geom geometry, target_srid integer)
RETURNS geometry AS $$
    SELECT ST_TransformPipeline(
        ST_Transform(geom, f.base_srid),
        enu_pipeline(f),
        f.srid
    )
    FROM ref_frame f WHERE f.srid = target_srid;
$$ LANGUAGE sql STABLE;

CREATE FUNCTION from_enu(geom geometry, out_srid integer)
RETURNS geometry AS $$
    SELECT ST_Transform(
        ST_InverseTransformPipeline(geom, enu_pipeline(f), f.base_srid),
        out_srid
    )
    FROM ref_frame f WHERE f.srid = ST_SRID(geom);
$$ LANGUAGE sql STABLE;
```

Requires 3D input — `ST_Force3D` if any geometry is 2D. A 2D point entering a topocentric transform is meaningless.

### 4.2 Reference — closed form

For validation. Forward:

```
X = (N + h)·cosφ·cosλ
Y = (N + h)·cosφ·sinλ
Z = (N(1 - e²) + h)·sinφ          N = a / √(1 - e² sin²φ)

[E]   [   -sinλ₀        cosλ₀        0   ] [X - X₀]
[N] = [-sinφ₀cosλ₀  -sinφ₀sinλ₀   cosφ₀ ] [Y - Y₀]
[U]   [ cosφ₀cosλ₀   cosφ₀sinλ₀   sinφ₀ ] [Z - Z₀]
```

Inverse: transpose the matrix (orthonormal), add `(X₀,Y₀,Z₀)`, then ECEF→geodetic via **Bowring's** closed-form (non-iterative, sub-mm for terrestrial heights).

Implement as `enu_fwd_ref(...)` / `enu_inv_ref(...)` in plpgsql, used only by tests.

---

## 5. Materialized ENU geometry

Do not transform on the fly in every query — store it, indexed:

```sql
ALTER TABLE gnss_obs ADD COLUMN geom_enu geometry(PointZ, 990001);

CREATE FUNCTION gnss_obs_fill_enu() RETURNS trigger AS $$
BEGIN
    NEW.geom_enu := to_enu(ST_Force3D(NEW.geom), 990001);
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_gnss_enu BEFORE INSERT OR UPDATE OF geom ON gnss_obs
    FOR EACH ROW EXECUTE FUNCTION gnss_obs_fill_enu();

CREATE INDEX gnss_obs_geom_enu_idx ON gnss_obs USING GIST (geom_enu);
```

Generated columns can't be used here (`to_enu` is only STABLE, not IMMUTABLE, since it reads `ref_frame`), hence the trigger.

---

## 6. QGIS integration

### 6.1 Register the SRID

QGIS reads unknown SRIDs from the database's `spatial_ref_sys`:

```sql
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, srtext, proj4text)
VALUES (990001, 'BELVEDERE', 990001, <wkt2>, <proj4text>);
```

### 6.2 The proj4text problem — and the fix

`+proj=pipeline` is an *operation*, not a CRS; it cannot go in `proj4text`. QGIS needs a real CRS definition.

**Use `+proj=ortho` as the QGIS-facing CRS.** Orthographic about the same origin is horizontally identical to topocentric ENU to well under a millimetre at this extent (radial scale error = 1 − cos c ≈ 1.1e-7 at 3 km ⇒ 0.3 mm):

```
+proj=ortho +lat_0=<lat_0> +lon_0=<lon_0> +x_0=<x_off> +y_0=<y_off>
  +ellps=GRS80 +units=m +no_defs
```

This is proj4-expressible, PROJ-native, and works in QGIS, GDAL, and PostGIS everywhere.

> **Vertical caveat — document this prominently.** `+proj=ortho` passes height through as **ellipsoidal h**, whereas topocentric **U is height above the tangent plane**. They differ by the Earth-curvature term `d²/2R` ≈ **0.7 m at 3 km**, 0.08 m at 1 km.
>
> Consequence: the 2D view in QGIS is exact, but Z read from an ortho-defined layer is **not** the ENU U. Keep the true 3D ENU (`geom_enu`, from the pipeline) as the authoritative photogrammetry frame; treat the ortho SRID as a horizontal display definition.
>
> If this ambiguity is unacceptable, register **two** SRIDs — `990001` (true 3D ENU, WKT2, for processing) and `990002` (ortho, for QGIS 2D) — and never mix them. Recommended.

### 6.3 QGIS side

- Layers load with the SRID; if QGIS still flags it as unknown, define a matching Custom CRS (Settings → Custom Projections) with the same proj4 string.
- Set project CRS to the ENU/ortho SRID and disable on-the-fly reprojection for these layers.
- Provide read-only views (`v_gnss_enu`, etc.) exposing `geom_enu` as the geometry column, so QGIS never touches the UTM originals.

---

## 7. Validation

Must all pass before the frame is marked `frozen`:

1. **Round-trip**: `from_enu(to_enu(p)) = p` to < 0.1 mm, over ~1000 points spanning the full extent.
2. **PROJ vs closed-form**: `to_enu` vs `enu_fwd_ref` agree to < 0.1 mm.
3. **Origin identity**: the origin mark transforms to exactly `(x_off, y_off, z_off)`.
4. **Scale check** — the one that catches real errors: for pairs of GNSS marks, ENU Euclidean distance vs ellipsoidal geodesic must agree to ~1 mm/km. A systematic **−0.7 mm/m** means the UTM scale factor leaked in (usually a missing `+inv +proj=utm`).
5. **Orthonormality**: rotation matrix `RᵀR = I` to 1e-12.
6. **Positivity**: min(E), min(N) over all data > 0 — confirms the false origin is large enough.
7. **Ortho vs topocentric**: horizontal difference < 1 mm; vertical difference matches `d²/2R` as predicted (confirms §6.2 is understood, not accidental).

---

## 8. Rollout

1. Audit datum realizations per campaign (§1.3). **Blocking** — do this first.
2. Normalize all source geometry to EPSG:7796.
3. Create `ref_frame`, insert the frame, generate pipeline + WKT2.
4. Implement both transform layers; run §7.
5. Only then: add `geom_enu`, backfill, index, add trigger.
6. Register SRID(s) in `spatial_ref_sys`; verify in QGIS.
7. Set `frozen = true`.
8. Export the frozen parameters to a plain-text file kept in version control alongside the Metashape projects — the database must not be the only place the origin exists.

---

## 9. To verify during implementation

- `SELECT postgis_full_version();` — need PostGIS ≥ 3.4 for `ST_TransformPipeline`, PROJ ≥ 8 for `+proj=topocentric`. If PROJ is older, the closed-form path becomes primary rather than a fallback.
- Whether the installed PROJ emits a usable WKT2 for the topocentric CRS: `projinfo -o WKT2:2019 "<pipeline>"`. If not, `srtext` can hold an Engineering CRS and QGIS relies on the ortho definition.
- Confirm ETRF2000 ↔ ITRF transformation grids/parameters are available if any campaign turns out to be ITRF-based.

---

## 10. Downstream benefit (Metashape / Blender)

With this frame in place:

- Metashape: convert GCPs and camera positions to ENU, set chunk CRS to **Local Coordinates (m)**, import. No projection, no scale factor, no grid convergence.
- Blender: coordinates already small and orthonormal — no export shift, no offset bookkeeping, and Blender's X/Y/Z **are** E/N/U, so camera azimuth reads as a true bearing.
- Camera pose export collapses to plain `cam.transform` rotation; the numeric-projection workaround for grid convergence becomes unnecessary.
