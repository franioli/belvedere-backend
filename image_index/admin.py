import json

from django import forms
from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.contrib.gis.forms import OSMWidget
from django.db.models import Count, Max, Min
from django.urls import reverse
from django.utils.html import format_html

from .models import Camera, CameraCalibration, Image

# ========== Cameras and Calibrations ==========


class CameraAdminForm(forms.ModelForm):
    class Meta:
        model = Camera
        fields = "__all__"
        widgets = {"location": OSMWidget(attrs={"map_width": 800, "map_height": 500})}


@admin.register(Camera)
class CameraAdmin(gis_admin.GISModelAdmin):
    form = CameraAdminForm
    prepopulated_fields = {"slug": ("camera_name",), }

    list_display = (
        "id",
        "camera_name",
        "serial_number",
        "model",
        "lens",
        "installation_date",
        "image_count",
        "min_image_date",
        "max_image_date",
        "image_count_link",
    )
    search_fields = ("camera_name", "serial_number", "model", "lens", "notes")
    list_filter = (
        "camera_name",
        "model",
        "lens",
        "installation_date",
        "created_at",
    )
    readonly_fields = ("id", "created_at")
    ordering = ("camera_name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _image_count=Count("images"),
            _min_image_date=Min("images__datetime"),
            _max_image_date=Max("images__datetime"),
        )

    @admin.display(ordering="_image_count", description="images")
    def image_count(self, obj):
        return getattr(obj, "_image_count", 0)

    @admin.display(ordering="_min_image_date", description="min_date")
    def min_image_date(self, obj):
        value = getattr(obj, "_min_image_date", None)
        return value.strftime("%Y-%m-%d %H:%M") if value else "No images"

    @admin.display(ordering="_max_image_date", description="max_date")
    def max_image_date(self, obj):
        value = getattr(obj, "_max_image_date", None)
        return value.strftime("%Y-%m-%d %H:%M") if value else "No images"

    @admin.display(description="images link")
    def image_count_link(self, obj):
        count = getattr(obj, "_image_count", 0)
        if count > 0:
            url = reverse("admin:image_index_image_changelist")
            return format_html(
                '<a href="{}?camera__id__exact={}">{} images</a>',
                url,
                obj.pk,
                count,
            )
        return "0 images"

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial["s3_bucket"] = "belvedere-images"
        return initial


@admin.register(CameraCalibration)
class CameraCalibrationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "camera",
        "calibration_date",
        "model_name",
        "model_id",
        "image_width_px",
        "image_height_px",
        "is_active",
    )
    list_filter = (
        "camera",
        "is_active",
        "calibration_date",
        "model_id",
    )
    search_fields = (
        "camera__camera_name",
        "camera__serial_number",
        "model_name",
        "notes",
    )
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("camera",)
    ordering = ("-calibration_date", "-id")

    def save_model(self, request, obj, form, change):
        if obj.is_active:
            CameraCalibration.objects.filter(camera=obj.camera, is_active=True).exclude(
                pk=obj.pk
            ).update(is_active=False)
        super().save_model(request, obj, form, change)


# ========== Filters based on datetime ==========


class BaseDateFilter(admin.SimpleListFilter):
    date_field = None

    @classmethod
    def create(cls, date_field):
        return type(
            f"{cls.__name__}_{date_field.replace('__', '_')}",
            (cls,),
            {"date_field": date_field},
        )


class YearFilterBase(BaseDateFilter):
    title = "year"
    parameter_name = "year"

    def lookups(self, request, model_admin):
        years = (
            model_admin.model.objects
            .exclude(**{f"{self.date_field}__isnull": True})
            .dates(self.date_field, "year")
            .values_list(f"{self.date_field}__year", flat=True)
        )
        return [(str(year), str(year)) for year in sorted(set(years), reverse=True)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{f"{self.date_field}__year": self.value()})
        return queryset


class MonthFilterBase(BaseDateFilter):
    title = "month"
    parameter_name = "month"

    def lookups(self, request, model_admin):
        return (
            ("1", "January"),
            ("2", "February"),
            ("3", "March"),
            ("4", "April"),
            ("5", "May"),
            ("6", "June"),
            ("7", "July"),
            ("8", "August"),
            ("9", "September"),
            ("10", "October"),
            ("11", "November"),
            ("12", "December"),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{f"{self.date_field}__month": self.value()})
        return queryset


class DayFilterBase(BaseDateFilter):
    title = "day"
    parameter_name = "day"

    def lookups(self, request, model_admin):
        return [(str(i), str(i)) for i in range(1, 32)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{f"{self.date_field}__day": self.value()})
        return queryset


class TimeOfDayFilterBase(BaseDateFilter):
    title = "time of day"
    parameter_name = "time_of_day"

    def lookups(self, request, model_admin):
        return tuple((str(i), f"{i:02d}:00 - {i + 1:02d}:00") for i in range(24))

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{f"{self.date_field}__hour": int(self.value())})
        return queryset


ImageYearFilter = YearFilterBase.create("datetime")
ImageMonthFilter = MonthFilterBase.create("datetime")
ImageDayFilter = DayFilterBase.create("datetime")
ImageTimeOfDayFilter = TimeOfDayFilterBase.create("datetime")


# ========== Image helpers ==========


FILE_SIZE_CLASSES_MB = {
    "large": (8, None),
    "medium": (5, 8),
    "small": (3, 5),
    "tiny": (0, 3),
}

FILE_SIZE_COLORMAP = {
    "large": "#090",
    "medium": "#f90",
    "small": "#d00",
    "tiny": "#999",
}


def get_file_size_color(size_mb):
    if size_mb is None:
        return "#999"
    for cls, (low, high) in FILE_SIZE_CLASSES_MB.items():
        if size_mb >= low and (high is None or size_mb < high):
            return FILE_SIZE_COLORMAP[cls]
    return "#999"


class FileSizeFilter(admin.SimpleListFilter):
    title = "file size"
    parameter_name = "file_size"

    def lookups(self, request, model_admin):
        return (
            ("large", "≥ 8 MB"),
            ("medium", "5–8 MB"),
            ("small", "3–5 MB"),
            ("tiny", "< 3 MB"),
            ("missing", "Missing"),
        )

    def queryset(self, request, queryset):
        mb = 1024 * 1024
        val = self.value()

        if val == "missing":
            return queryset.filter(file_size_bytes__isnull=True)

        if val in FILE_SIZE_CLASSES_MB:
            low_mb, high_mb = FILE_SIZE_CLASSES_MB[val]
            qs = queryset.filter(file_size_bytes__isnull=False).filter(
                file_size_bytes__gte=int(low_mb * mb)
            )
            if high_mb is not None:
                qs = qs.filter(file_size_bytes__lt=int(high_mb * mb))
            return qs

        return queryset


class PreviewWidget(forms.TextInput):
    def __init__(self, attrs=None, image_url=None):
        super().__init__(attrs)
        self.image_url = image_url

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs=attrs, renderer=renderer)
        if self.image_url:
            preview = format_html(
                '<div style="margin-top:6px;"><img src="{}" '
                'style="max-width:220px; max-height:140px; border:1px solid #ddd; border-radius:4px;" '
                'alt="preview" /></div>',
                self.image_url,
            )
            return format_html("{}{}", input_html, preview)
        return input_html


class ImageAdminForm(forms.ModelForm):
    class Meta:
        model = Image
        exclude = ("exif_data",)

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)

        if instance and getattr(instance, "exif_data", None):
            try:
                self.formatted_exif_initial = json.dumps(
                    instance.exif_data, indent=2, ensure_ascii=False, sort_keys=True
                )
            except (TypeError, ValueError):
                self.formatted_exif_initial = None

        preview_url = None
        try:
            if instance and instance.pk:
                preview_url = reverse("serve_image", args=[instance.pk])
        except Exception:
            preview_url = None

        if "object_key" in self.fields:
            self.fields["object_key"].widget = PreviewWidget(
                attrs={"size": 80}, image_url=preview_url
            )


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    form = ImageAdminForm
    list_display = (
        "id",
        "camera",
        "datetime",
        "filename",
        "label",
        "bucket",
        "rotation",
        "width_px",
        "height_px",
        "file_size_display",
        "view_image",
    )
    list_filter = (
        "camera",
        "rotation",
        "label",
        "bucket",
        ImageYearFilter,
        ImageMonthFilter,
        ImageDayFilter,
        ImageTimeOfDayFilter,
        FileSizeFilter,
    )
    search_fields = (
        "id",
        "camera__camera_name",
        "filename",
        "object_key",
        "bucket",
        "label",
        "s3_etag",
    )
    date_hierarchy = "datetime"
    readonly_fields = (
        "id",
        "indexed_at",
        "updated_at",
        "file_size_bytes",
        "formatted_exif_data",
        "file_path",
    )
    autocomplete_fields = ("camera",)
    ordering = ("-datetime", "-id")
    list_select_related = ("camera",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("camera")

    @admin.display(ordering="file_size_bytes", description="File size")
    def file_size_display(self, obj):
        size_mb = obj.file_size_mb if hasattr(obj, "file_size_mb") else None
        if size_mb is None:
            return format_html('<span style="color:#999;">Not found</span>')
        color = get_file_size_color(size_mb)
        return format_html(
            '<span style="color:{}; font-weight:bold;">{:.1f} MB</span>',
            color,
            size_mb,
        )

    @admin.display(description="EXIF data")
    def formatted_exif_data(self, obj):
        if obj.exif_data:
            try:
                formatted_json = json.dumps(
                    obj.exif_data, indent=2, ensure_ascii=False, sort_keys=True
                )
                return format_html(
                    '<pre style="background:#f8f8f8; padding:10px; border:1px solid #ddd; '
                    "border-radius:4px; font-family:monospace; font-size:12px; "
                    'max-height:400px; overflow-y:auto;">{}</pre>',
                    formatted_json,
                )
            except (TypeError, ValueError):
                return format_html(
                    '<pre style="background:#fff2f2; padding:10px; border:1px solid #fdd; '
                    'border-radius:4px; color:#d00;">Invalid JSON data</pre>'
                )
        return "No EXIF data"

    @admin.display(description="View image")
    def view_image(self, obj):
        try:
            url = reverse("serve_image", args=[obj.pk])
            return format_html('<a href="{}" target="_blank">View Image</a>', url)
        except Exception:
            return "-"
