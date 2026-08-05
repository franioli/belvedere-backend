"""Definition of local (topocentric ENU) reference frames.

A frame is described by *structured parameters* — origin, ellipsoid, false
origin. The PROJ pipeline string is a **derived, generated column**, so it can
never drift from the parameters, not even when a row is written straight from
QGIS or psql.
"""

import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Cast

from georef.constants import (
    ELLIPSOIDS,
    LOCAL_SRID_MAX,
    LOCAL_SRID_MIN,
    PROJECT_SRID,
)

#: Parameters that define the frame geometry. Changing any of them changes the
#: meaning of every coordinate ever expressed in the frame, so they are locked
#: once `frozen` is set.
FROZEN_GUARDED_FIELDS = (
    "lat_0",
    "lon_0",
    "h_0",
    "x_off",
    "y_off",
    "z_off",
    "ellps",
)


class SqlConcat(models.Func):
    """String concatenation via the `||` operator.

    Postgres' `concat()` — which Django's `Concat` compiles to — is STABLE and
    is therefore rejected inside a generated column. `||` on text is IMMUTABLE.
    """

    template = "(%(expressions)s)"
    arg_joiner = " || "
    output_field = models.TextField()


def _text(field_name: str) -> Cast:
    """Cast a float column to text with full round-trip precision.

    Postgres 12+ renders float8 with the shortest representation that reads
    back exactly, so the pipeline carries the full double precision of the
    origin — hand-formatting to a fixed number of decimals costs micrometres.
    """
    return Cast(models.F(field_name), models.TextField())


PROJ_PIPELINE_EXPRESSION = SqlConcat(
    models.Value("+proj=pipeline"),
    models.Value(" +step +proj=cart +ellps="),
    models.F("ellps"),
    models.Value(" +step +proj=topocentric +ellps="),
    models.F("ellps"),
    models.Value(" +lat_0="),
    _text("lat_0"),
    models.Value(" +lon_0="),
    _text("lon_0"),
    models.Value(" +h_0="),
    _text("h_0"),
    models.Value(" +step +proj=affine +xoff="),
    _text("x_off"),
    models.Value(" +yoff="),
    _text("y_off"),
    models.Value(" +zoff="),
    _text("z_off"),
)


class ReferenceFrame(models.Model):
    """A local topocentric ENU frame, identified by its own private SRID.

    Frames are immutable once `frozen`: a correction means inserting a *new*
    row with a *new* SRID, never updating this one, otherwise every historical
    coordinate silently changes meaning.
    """

    srid = models.IntegerField(
        primary_key=True,
        help_text=(
            f"SRID of the frame, in the private range "
            f"{LOCAL_SRID_MIN}–{LOCAL_SRID_MAX}. Also the SRID of the "
            f"matching spatial_ref_sys row."
        ),
    )
    name = models.CharField(
        max_length=64,
        unique=True,
        help_text="Short stable identifier, e.g. 'belvedere-enu'.",
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="What this frame is for and over which area it is valid.",
    )

    # ---- origin (canonical parameters) ----
    origin_mark = models.CharField(
        max_length=45,
        help_text="Label of the GNSS monument the origin sits on, e.g. 'D12'.",
    )
    lat_0 = models.FloatField(help_text="Origin latitude in degrees.")
    lon_0 = models.FloatField(help_text="Origin longitude in degrees.")
    h_0 = models.FloatField(
        help_text="Origin height in metres — ELLIPSOIDAL, never orthometric."
    )
    ellps = models.CharField(
        max_length=16,
        default="GRS80",
        choices=[(key, key) for key in ELLIPSOIDS],
        help_text="Reference ellipsoid name as understood by PROJ.",
    )

    # ---- false origin ----
    x_off = models.FloatField(
        default=0.0, help_text="Added to East so coordinates stay positive."
    )
    y_off = models.FloatField(
        default=0.0, help_text="Added to North so coordinates stay positive."
    )
    z_off = models.FloatField(default=0.0, help_text="Added to Up.")

    # ---- provenance ----
    base_srid = models.IntegerField(
        default=PROJECT_SRID,
        help_text="CRS the origin coordinates were taken from.",
    )
    datum_epoch = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Datum realisation epoch as a decimal year, e.g. 2008.00.",
    )
    valid_from = models.DateField(default=datetime.date.today)
    frozen = models.BooleanField(
        default=False,
        help_text=(
            "Once set, the origin and offsets can no longer change. "
            "Corrections require a new SRID."
        ),
    )
    notes = models.TextField(blank=True, null=True)

    # ---- derived ----
    proj_pipeline = models.GeneratedField(
        expression=PROJ_PIPELINE_EXPRESSION,
        output_field=models.TextField(),
        db_persist=True,
        help_text="PROJ pipeline generated from the parameters. Never hand-edited.",
    )

    class Meta:
        db_table = "georef_reference_frame"
        verbose_name = "reference frame"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(srid__gte=LOCAL_SRID_MIN, srid__lte=LOCAL_SRID_MAX),
                name="reference_frame_srid_in_private_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (SRID {self.srid})"

    @property
    def ellipsoid(self) -> tuple[float, float]:
        """Semi-major axis and inverse flattening of the frame's ellipsoid."""
        return ELLIPSOIDS[self.ellps]

    def save(self, *args, **kwargs) -> None:
        """Refuse in-place edits of a frozen frame's geometry parameters.

        The database trigger is the real enforcement (QGIS and psql bypass
        Django); this only turns the violation into a readable admin error.
        """
        if not self._state.adding:
            previous = (
                type(self)
                .objects.filter(pk=self.pk)
                .values("frozen", *FROZEN_GUARDED_FIELDS)
                .first()
            )
            if previous and previous["frozen"]:
                changed = [
                    field
                    for field in FROZEN_GUARDED_FIELDS
                    if previous[field] != getattr(self, field)
                ]
                if changed:
                    raise ValidationError(
                        f"Reference frame {self.srid} is frozen; "
                        f"cannot change {', '.join(changed)}. "
                        f"Define a new SRID instead."
                    )
        super().save(*args, **kwargs)
