from django.contrib.gis.db import models

# ================ Survey and Instrument Models ================


class Survey(models.Model):
    id = models.IntegerField(primary_key=True)
    date = models.DateField(blank=True, null=True)
    year = models.BigIntegerField(blank=True, null=True)
    notes = models.CharField(max_length=254, blank=True, null=True)

    class Meta:
        db_table = "surveys"


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


# ================ GNSS Measurement Models ================


class Point(models.Model):
    id = models.IntegerField(primary_key=True)
    label = models.CharField(max_length=45, blank=True, null=True)
    active = models.BooleanField(blank=True, null=True)
    is_fixed = models.BooleanField(blank=True, null=True)
    ref_date = models.DateField(blank=True, null=True)
    first_survey_date = models.DateField(blank=True, null=True)
    last_survey_date = models.DateField(blank=True, null=True)
    num_measurements = models.BigIntegerField(blank=True, null=True)
    notes = models.CharField(max_length=512, blank=True, null=True)

    class Meta:
        db_table = "points"


class Measurement(models.Model):
    id = models.IntegerField(primary_key=True)
    geom = models.PointField(srid=32632, blank=True, null=True)
    east = models.FloatField()
    north = models.FloatField()
    h = models.FloatField()
    point = models.ForeignKey(Point, models.DO_NOTHING, db_column="point")
    survey = models.ForeignKey(Survey, models.DO_NOTHING, db_column="survey")
    point_photo = models.ForeignKey(
        "Photo", models.DO_NOTHING, db_column="point_photo", blank=True, null=True
    )
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


class Photo(models.Model):
    id = models.IntegerField(primary_key=True)
    path = models.CharField(max_length=254, blank=True, null=True)
    file_name = models.CharField(max_length=254, blank=True, null=True)
    image = models.BinaryField(blank=True, null=True)

    class Meta:
        db_table = "photo"


# ================ DIC Velocity Data Models ================

# ================ Product Models ================
