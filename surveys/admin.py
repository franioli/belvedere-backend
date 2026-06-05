from django.contrib import admin
from django.contrib.gis import admin as gis_admin

from .models import (
    Flight,
    Instrument,
    Measurement,
    Photo,
    Point,
    Survey,
    SurveyHasInstrument,
)


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "year", "notes")
    search_fields = ("id", "year", "notes")
    list_filter = ("year", "date")
    ordering = ("-year", "-date")


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "brand", "year_of_m", "reseller")
    search_fields = ("id", "name", "type", "brand", "reseller")
    list_filter = ("type", "brand", "year_of_m")
    ordering = ("name",)


@admin.register(SurveyHasInstrument)
class SurveyHasInstrumentAdmin(admin.ModelAdmin):
    list_display = ("id", "fk_surveys", "fk_instrum")
    search_fields = ("id", "fk_surveys__id", "fk_instrum__name", "fk_instrum__brand")
    list_filter = ("fk_surveys", "fk_instrum")
    raw_id_fields = ("fk_surveys", "fk_instrum")
    ordering = ("id",)


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "fk_surveys",
        "camera_nam",
        "n_images",
        "average_he",
        "average_gs",
        "global_acc",
    )
    search_fields = ("id", "camera_nam", "fk_surveys__id")
    list_filter = ("fk_surveys", "camera_nam")
    raw_id_fields = ("fk_surveys",)
    ordering = ("id",)


@admin.register(Point)
class PointAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "label",
        "active",
        "is_fixed",
        "ref_date",
        "first_survey_date",
        "last_survey_date",
        "num_measurements",
    )
    search_fields = ("id", "label", "notes")
    list_filter = (
        "active",
        "is_fixed",
        "ref_date",
        "first_survey_date",
        "last_survey_date",
    )
    ordering = ("label", "id")


@admin.register(Measurement)
class MeasurementAdmin(gis_admin.GISModelAdmin):
    list_display = (
        "id",
        "point",
        "survey",
        "meas_date",
        "east",
        "north",
        "h",
        "meas_strategy",
    )
    search_fields = (
        "id",
        "point__label",
        "point__id",
        "survey__id",
        "notes",
        "meas_strategy",
    )
    list_filter = ("survey", "meas_date", "meas_strategy")
    raw_id_fields = ("point", "survey", "point_photo")
    ordering = ("-meas_date", "-id")
    readonly_fields = ("geom",)


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "path")
    search_fields = ("id", "file_name", "path")
    ordering = ("file_name",)
