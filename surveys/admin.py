from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.contrib.gis.forms.widgets import OSMWidget
from django.db.models import Count, Max, Min, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from import_export.admin import ImportExportMixin

from .models import (
    ActivePoint,
    Flight,
    Instrument,
    Measurement,
    MeasurementPhoto,
    Point,
    PointsMeasurement,
    PointsMovementFiltered,
    PointsMovementRaw,
    Product2D,
    Product3D,
    Survey,
    SurveyHasInstrument,
    Volume,
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
        "notes",
    )
    search_fields = ("id", "label", "notes")
    list_filter = ("active", "is_fixed", "ref_date")
    ordering = ("label", "id")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Point]:
        return (
            super()
            .get_queryset(request)
            .annotate(
                _first_survey_date=Min("measurement__survey__date"),
                _last_survey_date=Max("measurement__survey__date"),
                _num_measurements=Count("measurement"),
            )
        )

    @admin.display(ordering="_first_survey_date", description="First survey date")
    def first_survey_date(self, obj: Point):
        return getattr(obj, "_first_survey_date", None)

    @admin.display(ordering="_last_survey_date", description="Last survey date")
    def last_survey_date(self, obj: Point):
        return getattr(obj, "_last_survey_date", None)

    @admin.display(ordering="_num_measurements", description="Measurements")
    def num_measurements(self, obj: Point):
        return getattr(obj, "_num_measurements", None)


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


class BaseProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "survey",
        "data_type",
        "file_format",
        "is_uploaded",
        "object_key",
        "file_size_bytes",
    )
    search_fields = ("id", "survey__id", "data_type", "object_key", "path")
    list_filter = ("data_type", "is_uploaded", "survey")
    raw_id_fields = ("survey",)
    readonly_fields = ("s3_etag", "s3_last_modified", "is_uploaded", "file_link")
    ordering = ("survey__year", "id")

    @admin.display(description="S3 URL")
    def file_link(self, obj):
        if obj and obj.file_path:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
                obj.file_path,
                obj.file_path,
            )
        return "-"


@admin.register(Product2D)
class Product2DAdmin(BaseProductAdmin):
    pass


@admin.register(Product3D)
class Product3DAdmin(BaseProductAdmin):
    pass


@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "survey_prev",
        "survey",
        "dv",
        "density",
        "density_uncertainty",
    )
    raw_id_fields = ("survey", "survey_prev")
    ordering = ("survey__year",)


class ReadOnlyViewAdmin(admin.ModelAdmin):
    """Browse-only admin for the unmanaged models mapped onto Postgres views."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(PointsMeasurement)
class PointsMeasurementAdmin(ReadOnlyViewAdmin):
    list_display = (
        "id",
        "label",
        "survey_year",
        "survey_date",
        "east",
        "north",
        "h",
        "h_orto",
        "is_fixed",
        "meas_strategy",
    )
    search_fields = ("label",)
    list_filter = ("survey_year", "is_fixed", "meas_strategy")
    ordering = ("-survey_year", "label")


class PointsMovementAdmin(ReadOnlyViewAdmin):
    list_display = (
        "label",
        "survey_year",
        "survey_date_prev",
        "survey_date_fin",
        "dt",
        "d",
        "v",
        "a",
    )
    search_fields = ("label",)
    list_filter = ("survey_year", "is_fixed")
    ordering = ("label", "-survey_date_fin")


@admin.register(PointsMovementRaw)
class PointsMovementRawAdmin(PointsMovementAdmin):
    pass


@admin.register(PointsMovementFiltered)
class PointsMovementFilteredAdmin(PointsMovementAdmin):
    pass


@admin.register(ActivePoint)
class ActivePointAdmin(ReadOnlyViewAdmin):
    list_display = (
        "label",
        "last_measure_date",
        "east",
        "north",
        "h",
        "is_fixed",
    )
    search_fields = ("label",)
    list_filter = ("is_fixed",)
    ordering = ("label",)
