from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.contrib.gis.forms.widgets import OSMWidget
from django.utils.html import format_html
from import_export.admin import ImportExportMixin

from .models import (
    Flight,
    Instrument,
    Measurement,
    MeasurementPhoto,
    Point,
    Survey,
    SurveyHasInstrument,
)
from .resources import MeasurementResource


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


class MapWidget(OSMWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs.update({"map_width": 800, "map_height": 500})


@admin.register(Measurement)
class MeasurementAdmin(ImportExportMixin, gis_admin.GISModelAdmin):
    resource_classes = [MeasurementResource]
    gis_widget = MapWidget

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
    raw_id_fields = ("point", "survey")
    ordering = ("-meas_date", "-id")
    readonly_fields = ()

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "point",
                    "survey",
                    "meas_date",
                    "meas_strategy",
                    "east",
                    "north",
                    "h",
                    "ds_east",
                    "ds_north",
                    "ds_h",
                    "lat",
                    "lon",
                    "h_orto",
                    "notes",
                )
            },
        ),
        (
            "Map",
            {
                "fields": ("geom",),
            },
        ),
    )


@admin.register(MeasurementPhoto)
class MeasurementPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "measurement", "file_name", "path", "image_preview")
    search_fields = ("id", "measurement__id", "file_name", "path")
    raw_id_fields = ("measurement",)
    readonly_fields = ("path", "file_name", "image_preview")
    fields = ("measurement", "image", "image_preview", "path", "file_name")

    def image_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">Open image</a><br>'
                '<img src="{}" style="max-height:220px; max-width:220px; border:1px solid #ccc;" />',
                obj.image.url,
                obj.image.url,
            )
        return "-"

    image_preview.short_description = "Preview"
