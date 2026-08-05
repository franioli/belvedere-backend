import os

from django.contrib.gis.db import models
from django.db.models.functions import Lower, Trim

from georef.constants import ENU_SRID, PROJECT_SRID
from surveys.sql import COLUMN_COMMENTS as DOC
from surveys.sql import TABLE_COMMENTS

# ================ Survey and Instrument Models ================


class Survey(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField(blank=True, null=True, db_comment=DOC["date"])
    year = models.BigIntegerField(blank=True, null=True, db_comment=DOC["year"])
    notes = models.CharField(
        max_length=254, blank=True, null=True, db_comment=DOC["notes"]
    )

    class Meta:
        db_table = "surveys"
        db_table_comment = TABLE_COMMENTS["surveys"]

    def __str__(self):
        return f"Survey {self.id} - {self.date}"


class Instrument(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=254, blank=True, null=True)
    type = models.CharField(max_length=254, blank=True, null=True)
    specificat = models.CharField(max_length=254, blank=True, null=True)
    brand = models.CharField(max_length=254, blank=True, null=True)
    year_of_m = models.BigIntegerField(blank=True, null=True)
    reseller = models.CharField(max_length=254, blank=True, null=True)

    class Meta:
        db_table = "instruments"

    def __str__(self):
        return f"Instrument {self.id} - {self.name}"


class SurveyHasInstrument(models.Model):
    id = models.AutoField(primary_key=True)
    fk_surveys = models.ForeignKey(
        Survey, models.DO_NOTHING, db_column="fk_surveys", blank=True, null=True
    )
    fk_instrum = models.ForeignKey(
        Instrument, models.DO_NOTHING, db_column="fk_instrum", blank=True, null=True
    )

    class Meta:
        db_table = "surveys_has_instruments"
        verbose_name = "Survey-Instrument association"


class Flight(models.Model):
    id = models.AutoField(primary_key=True)
    fk_surveys = models.ForeignKey(Survey, models.DO_NOTHING, db_column="fk_surveys")
    average_height = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    n_images = models.BigIntegerField(blank=True, null=True)
    n_controlpoints = models.BigIntegerField(blank=True, null=True)
    n_checkpoints = models.BigIntegerField(blank=True, null=True)
    average_gsd = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    camera_name = models.CharField(max_length=254, blank=True, null=True)
    focal_length = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    sensor_size = models.CharField(max_length=254, blank=True, null=True)
    image_size = models.CharField(max_length=254, blank=True, null=True)
    pixel_size = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    global_accuracy = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    x_accuracy = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    y_accuracy = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    z_accuracy = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )

    class Meta:
        db_table = "flights"

    def __str__(self):
        return f"Flight {self.id} - Survey {self.fk_surveys_id}"


# ================ GNSS Measurement Models ================


class Point(models.Model):
    id = models.AutoField(primary_key=True)
    label = models.CharField(
        max_length=45, blank=True, null=True, db_comment=DOC["label"]
    )
    active = models.BooleanField(blank=True, null=True, db_comment=DOC["active"])
    is_fixed = models.BooleanField(blank=True, null=True, db_comment=DOC["is_fixed"])
    ref_date = models.DateField(blank=True, null=True, db_comment=DOC["ref_date"])
    notes = models.CharField(
        max_length=512, blank=True, null=True, db_comment=DOC["notes"]
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        db_table = "points"
        db_table_comment = TABLE_COMMENTS["points"]
        constraints = [
            # The pre-existing unique index on `label` is case-sensitive, which
            # is how the 2026 import created D01BIS next to D01bis. Matches the
            # key `merge_duplicate_points` groups by.
            models.UniqueConstraint(
                Lower(Trim("label")), name="points_label_unique_ci"
            ),
        ]

    def __str__(self):
        return f"Point {self.label} (ID {self.id})"


class Measurement(models.Model):
    id = models.AutoField(primary_key=True)
    geom = models.PointField(
        srid=PROJECT_SRID, blank=True, null=True, db_comment=DOC["geom"]
    )
    east = models.FloatField(db_comment=DOC["east"])
    north = models.FloatField(db_comment=DOC["north"])
    h = models.FloatField(verbose_name="h (ellipsoidal)", db_comment=DOC["h"])
    point = models.ForeignKey(Point, models.DO_NOTHING, db_column="point")
    survey = models.ForeignKey(Survey, models.DO_NOTHING, db_column="survey")
    meas_date = models.DateField(blank=True, null=True, db_comment=DOC["meas_date"])
    std_east = models.FloatField(
        blank=True, null=True, verbose_name="std east", db_comment=DOC["std_east"]
    )
    std_north = models.FloatField(
        blank=True, null=True, verbose_name="std north", db_comment=DOC["std_north"]
    )
    std_h = models.FloatField(
        blank=True, null=True, verbose_name="std h", db_comment=DOC["std_h"]
    )
    meas_strategy = models.CharField(
        max_length=25, blank=True, null=True, db_comment=DOC["meas_strategy"]
    )
    meas_time = models.DateTimeField(blank=True, null=True, db_comment=DOC["meas_time"])
    notes = models.CharField(
        max_length=250, blank=True, null=True, db_comment=DOC["notes"]
    )
    lat = models.FloatField(blank=True, null=True, db_comment=DOC["lat"])
    lon = models.FloatField(blank=True, null=True, db_comment=DOC["lon"])
    h_orto = models.FloatField(blank=True, null=True, db_comment=DOC["h_orto"])
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    geom_enu = models.PointField(
        dim=3,
        srid=ENU_SRID,
        blank=True,
        null=True,
        editable=False,
        help_text=(
            "Position in the local ENU frame, filled by a database trigger "
            "from east/north/h. Read-only: edit the source coordinates instead."
        ),
        db_comment=DOC["geom_enu"],
    )

    # A realization mismatch between campaigns would look exactly like glacier
    # motion, so it is recorded rather than assumed. The SRID is not stored —
    # `geom` already carries it.
    datum_realization = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        choices=[
            ("RDN2008", "RDN2008 (ETRF2000, epoch 2008.0)"),
            ("ETRF2000", "ETRF2000"),
            ("ITRF2014", "ITRF2014"),
        ],
        help_text="Reference frame realization the campaign was processed in.",
        db_comment=DOC["datum_realization"],
    )
    height_type = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        choices=[("ellipsoidal", "ellipsoidal"), ("orthometric", "orthometric")],
        help_text="Should be 'ellipsoidal' everywhere; h_orto is computed internally from h using ITALGEO05 geoid model.",
        db_comment=DOC["height_type"],
    )

    class Meta:
        db_table = "measurements"
        db_table_comment = TABLE_COMMENTS["measurements"]

    def __str__(self):
        return (
            f"Measurement {self.id} - Point {self.point_id} @ Survey {self.survey_id}"
        )


def measurement_photo_upload_to(instance, filename):
    measurement_id = instance.measurement_id or "unassigned"
    _, ext = os.path.splitext(filename)
    ext = ext.lower() or ".jpg"
    return f"measurements/{measurement_id}/photos/measurement_{measurement_id}{ext}"


class MeasurementPhoto(models.Model):
    id = models.AutoField(primary_key=True)
    measurement = models.OneToOneField(
        "Measurement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photo",
    )
    image = models.ImageField(
        upload_to=measurement_photo_upload_to,
        blank=True,
        null=True,
    )
    path = models.CharField(max_length=254, blank=True, null=True, editable=False)
    file_name = models.CharField(max_length=254, blank=True, null=True, editable=False)

    class Meta:
        db_table = "measurement_photos"
        verbose_name = "Measurement Monograph Photo"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        updates = []
        if self.image:
            if self.path != self.image.name:
                self.path = self.image.name
                updates.append("path")

            filename = os.path.basename(self.image.name)
            if self.file_name != filename:
                self.file_name = filename
                updates.append("file_name")

        if updates:
            super().save(update_fields=updates)

    def __str__(self):
        return f"MeasurementPhoto {self.pk} - Measurement {self.measurement_id}"


# ================ Survey Products and Volumes ================


class Product2D(models.Model):
    """Raster product of a survey (orthophoto, DSM, ...) served via WMS."""

    survey = models.ForeignKey(
        Survey,
        on_delete=models.PROTECT,
        related_name="products_2d",
    )
    data_type = models.CharField(
        max_length=64,
        help_text="Product type, e.g. ortofoto, dsm.",
    )
    file_format = models.CharField(max_length=32, blank=True, null=True)
    reference_system = models.CharField(max_length=254, blank=True, null=True)
    epsg = models.IntegerField(blank=True, null=True)
    proj4 = models.CharField(max_length=512, blank=True, null=True)
    bounding_box = models.CharField(max_length=254, blank=True, null=True)
    license = models.CharField(max_length=64, blank=True, null=True)
    pixel_size = models.FloatField(
        blank=True, null=True, help_text="Ground pixel size in metres."
    )
    n_bands = models.IntegerField(blank=True, null=True)
    wms_url = models.URLField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="WMS endpoint URL on GeoServer.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_2d"
        verbose_name = "2D product"

    def __str__(self) -> str:
        return f"Product2D {self.pk} - {self.data_type} (survey {self.survey_id})"


class Product3D(models.Model):
    """3D product of a survey (point cloud, mesh, ...) with a direct URL."""

    survey = models.ForeignKey(
        Survey,
        on_delete=models.PROTECT,
        related_name="products_3d",
    )
    data_type = models.CharField(
        max_length=64,
        help_text="Product type, e.g. pointcloud, mesh.",
    )
    file_format = models.CharField(max_length=32, blank=True, null=True)
    reference_system = models.CharField(max_length=254, blank=True, null=True)
    epsg = models.IntegerField(blank=True, null=True)
    bounding_box = models.CharField(max_length=254, blank=True, null=True)
    license = models.CharField(max_length=64, blank=True, null=True)
    average_point_spacing = models.FloatField(
        blank=True, null=True, help_text="Average point spacing in metres."
    )
    n_points = models.BigIntegerField(blank=True, null=True)
    n_nodes = models.BigIntegerField(blank=True, null=True)
    n_scalar_fields = models.IntegerField(blank=True, null=True)
    url = models.URLField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="Direct URL to the COPC point cloud (Zenodo, S3, etc.).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_3d"
        verbose_name = "3D product"

    def __str__(self) -> str:
        return f"Product3D {self.pk} - {self.data_type} (survey {self.survey_id})"


class Volume(models.Model):
    """Glacier volume variation between two consecutive surveys."""

    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="volumes")
    survey_prev = models.ForeignKey(
        Survey, on_delete=models.PROTECT, related_name="volumes_as_previous"
    )
    dv = models.FloatField(help_text="Volume difference in cubic metres.")
    density = models.FloatField(blank=True, null=True, help_text="Density in kg/m³.")
    density_uncertainty = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "volumes"

    def __str__(self):
        return f"Volume {self.pk} - surveys {self.survey_prev_id}→{self.survey_id}"


# ================ Database views (read-only) ================
# Unmanaged models over the Postgres views created in migration 0011.
# Django never writes to them; any change to a view definition must go
# through a new migration.


class PointsMeasurement(models.Model):
    """Row of the `points_measurements` view (measurement + point + survey join)."""

    id = models.IntegerField(primary_key=True)
    label = models.CharField(max_length=45)
    point_id = models.IntegerField()
    is_active = models.BooleanField(null=True)
    is_fixed = models.BooleanField()
    east = models.FloatField()
    north = models.FloatField()
    h = models.FloatField(verbose_name="h (ellipsoidal)")
    h_orto = models.FloatField(null=True)
    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)
    survey_id = models.IntegerField()
    survey_date = models.DateField(null=True)
    survey_year = models.BigIntegerField(null=True)
    meas_date = models.DateField(null=True)
    meas_time = models.DateTimeField(null=True)
    meas_strategy = models.CharField(max_length=25, null=True)
    std_east = models.FloatField(null=True)
    std_north = models.FloatField(null=True)
    std_h = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = "points_measurements"
        verbose_name = "Points measurement (read-only view)"
        verbose_name_plural = "Points measurements (read-only view)"

    def __str__(self):
        return f"{self.label} @ {self.survey_year}"


class PointsMovementBase(models.Model):
    """Common columns of the `points_movement_*` views."""

    id = models.IntegerField(primary_key=True)
    label = models.CharField(max_length=45)
    survey_year = models.BigIntegerField(null=True)
    is_fixed = models.BooleanField()
    survey_date_fin = models.DateField(null=True)
    survey_date_prev = models.DateField(null=True)
    dt = models.IntegerField(help_text="Days between the two surveys.")
    d_e = models.FloatField()
    d_n = models.FloatField()
    d_h = models.FloatField()
    d = models.FloatField(help_text="3D displacement in metres.")
    v = models.FloatField(help_text="Velocity in m/day.")
    a = models.FloatField(help_text="Acceleration in m/day².")

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.label} {self.survey_date_prev}→{self.survey_date_fin}"


class PointsMovementRaw(PointsMovementBase):
    class Meta(PointsMovementBase.Meta):
        managed = False
        db_table = "points_movement_raw"
        verbose_name = "Points movement raw (read-only view)"
        verbose_name_plural = "Points movements raw (read-only view)"


class PointsMovementFiltered(PointsMovementBase):
    class Meta(PointsMovementBase.Meta):
        managed = False
        db_table = "points_movement_filtered"
        verbose_name = "Points movement filtered (read-only view)"
        verbose_name_plural = "Points movements filtered (read-only view)"


class ActivePoint(models.Model):
    """Row of the `active_points` view (latest measurement per active point)."""

    meas_id = models.IntegerField(primary_key=True)
    label = models.CharField(max_length=45)
    last_measure_date = models.DateField(null=True)
    east = models.FloatField()
    north = models.FloatField()
    h = models.FloatField(verbose_name="h (ellipsoidal)")
    is_fixed = models.BooleanField()

    class Meta:
        managed = False
        db_table = "active_points"
        verbose_name = "Active point (read-only view)"
        verbose_name_plural = "Active points (read-only view)"

    def __str__(self):
        return f"{self.label} ({self.last_measure_date})"


# =========== Unmanaged legacy tables (NOT modelled in Django) ==============

#   - scatter_points, scatter_measurements: legacy scatter manual displacement points kept in the DB for reference.
#   - layer_styles, qgis_projects: owned and managed by QGIS.
#   - raster.geoid_model: geoid raster sampled by the compute_measurement_geometry
#     trigger (maintained outside Django).
