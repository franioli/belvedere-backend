import os
from urllib.parse import quote

from django.conf import settings
from django.contrib.gis.db import models

# ================ Survey and Instrument Models ================


class Survey(models.Model):
    id = models.IntegerField(primary_key=True)
    date = models.DateField(blank=True, null=True)
    year = models.BigIntegerField(blank=True, null=True)
    notes = models.CharField(max_length=254, blank=True, null=True)

    class Meta:
        db_table = "surveys"

    def __str__(self):
        return f"Survey {self.id} - {self.date}"


class Instrument(models.Model):
    id = models.IntegerField(primary_key=True)
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
    id = models.IntegerField(primary_key=True)
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
    id = models.IntegerField(primary_key=True)
    fk_surveys = models.ForeignKey(Survey, models.DO_NOTHING, db_column="fk_surveys")
    average_he = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    n_images = models.BigIntegerField(blank=True, null=True)
    n_controlp = models.BigIntegerField(blank=True, null=True)
    n_checkpoi = models.BigIntegerField(blank=True, null=True)
    average_gs = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    camera_nam = models.CharField(max_length=254, blank=True, null=True)
    focal_leng = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    sensor_siz = models.CharField(max_length=254, blank=True, null=True)
    image_size = models.CharField(max_length=254, blank=True, null=True)
    pixel_size = models.DecimalField(
        max_digits=10, decimal_places=5, blank=True, null=True
    )
    global_acc = models.DecimalField(
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
    id = models.IntegerField(primary_key=True)
    label = models.CharField(max_length=45, blank=True, null=True)
    active = models.BooleanField(blank=True, null=True)
    is_fixed = models.BooleanField(blank=True, null=True)
    ref_date = models.DateField(blank=True, null=True)
    notes = models.CharField(max_length=512, blank=True, null=True)

    class Meta:
        db_table = "points"

    def __str__(self):
        return f"Point {self.id} - {self.label}"


class Measurement(models.Model):
    id = models.IntegerField(primary_key=True)
    geom = models.PointField(srid=32632, blank=True, null=True)
    east = models.FloatField()
    north = models.FloatField()
    h = models.FloatField()
    point = models.ForeignKey(Point, models.DO_NOTHING, db_column="point")
    survey = models.ForeignKey(Survey, models.DO_NOTHING, db_column="survey")
    meas_date = models.DateField(blank=True, null=True)
    ds_east = models.FloatField(blank=True, null=True)
    ds_north = models.FloatField(blank=True, null=True)
    ds_h = models.FloatField(blank=True, null=True)
    meas_strategy = models.CharField(max_length=25, blank=True, null=True)
    meas_time = models.DateTimeField(blank=True, null=True)
    notes = models.CharField(max_length=250, blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    h_orto = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "measurements"


def measurement_photo_upload_to(instance, filename):
    measurement_id = instance.measurement_id or "unassigned"
    _, ext = os.path.splitext(filename)
    ext = ext.lower() or ".jpg"
    return f"measurements/{measurement_id}/photos/measurement_{measurement_id}{ext}"


class MeasurementPhoto(models.Model):
    id = models.IntegerField(primary_key=True)  # keep as-is
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


class BaseProduct(models.Model):
    """Common metadata for survey data products stored on S3.

    Suggested S3 key convention inside the products bucket:
    ``<db_table>/<survey_year>/<filename>`` (e.g. ``products_2d/1977/1977_ortofoto_50cm.tif``).
    """

    survey = models.ForeignKey(
        Survey,
        on_delete=models.PROTECT,
        related_name="%(class)s_products",
    )
    data_type = models.CharField(
        max_length=64,
        help_text="Product type, e.g. ortofoto, dsm, pointcloud, mesh.",
    )
    file_format = models.CharField(max_length=32, blank=True, null=True)
    reference_system = models.CharField(max_length=254, blank=True, null=True)
    epsg = models.IntegerField(blank=True, null=True)
    proj4 = models.CharField(max_length=512, blank=True, null=True)
    bounding_box = models.CharField(max_length=254, blank=True, null=True)
    license = models.CharField(max_length=64, blank=True, null=True)
    path = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Legacy local file path (pre-S3).",
    )

    # S3 object reference (mirrors image_index.Image)
    bucket = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="S3 bucket containing the product object. Null until uploaded.",
    )
    object_key = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="Full S3 object key inside the bucket. Null until uploaded.",
    )
    s3_etag = models.CharField(max_length=128, blank=True, null=True)
    s3_last_modified = models.DateTimeField(blank=True, null=True)
    file_size_bytes = models.BigIntegerField(blank=True, null=True)
    is_uploaded = models.BooleanField(
        default=False,
        help_text="Whether the product file is present in S3 (set by index_s3_products).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["bucket", "object_key"],
                name="unique_%(class)s_bucket_object_key",
            ),
        ]

    @property
    def file_path(self) -> str:
        """Public URL of the S3 object, empty if not uploaded yet."""
        endpoint = (getattr(settings, "S3_ENDPOINT_URL", "") or "").rstrip("/")
        if not endpoint or not self.bucket or not self.object_key:
            return ""
        return f"{endpoint}/{self.bucket}/{quote(self.object_key, safe='/')}"

    def __str__(self):
        return f"{type(self).__name__} {self.pk} - {self.data_type} (survey {self.survey_id})"


class Product2D(BaseProduct):
    """Raster product of a survey (orthophoto, DSM, ...)."""

    pixel_size = models.FloatField(
        blank=True, null=True, help_text="Ground pixel size in metres."
    )
    n_bands = models.IntegerField(blank=True, null=True)

    class Meta(BaseProduct.Meta):
        db_table = "products_2d"
        verbose_name = "2D product"


class Product3D(BaseProduct):
    """3D product of a survey (point cloud, mesh, ...)."""

    average_point_spacing = models.FloatField(
        blank=True, null=True, help_text="Average point spacing in metres."
    )
    n_points = models.BigIntegerField(blank=True, null=True)
    n_nodes = models.BigIntegerField(blank=True, null=True)
    n_scalar_fields = models.IntegerField(blank=True, null=True)
    texture = models.BooleanField(
        blank=True, null=True, help_text="Whether the mesh has a texture."
    )

    class Meta(BaseProduct.Meta):
        db_table = "products_3d"
        verbose_name = "3D product"


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


# Unmanaged legacy tables (NOT modelled in Django):
#   - scatter_points, scatter_measurements: legacy scatter manual displacement points kept in the DB for reference.
#   - layer_styles, qgis_projects: owned and managed by QGIS.
#   - raster.geoid_model: geoid raster sampled by the compute_measurement_geometry
#     trigger (maintained outside Django).
