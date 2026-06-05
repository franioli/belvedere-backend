# survey/resources.py
import logging

from django.contrib.gis.geos import Point as GEOSPoint
from django.core.exceptions import ValidationError
from import_export import fields, resources
from import_export.widgets import DateWidget

from .models import Measurement, Point, Survey

logger = logging.getLogger(__name__)


class MeasurementResource(resources.ModelResource):
    meas_date = fields.Field(
        column_name="meas_date",
        attribute="meas_date",
        widget=DateWidget(format="%Y-%m-%d"),
    )

    class Meta:
        model = Measurement
        fields = (
            "id",
            "point",
            "survey",
            "east",
            "north",
            "h",
            "meas_date",
            "notes",
            "ds_east",
            "ds_north",
            "ds_h",
            "meas_strategy",
            "lat",
            "lon",
            "h_orto",
        )
        import_id_fields = ()
        skip_unchanged = False
        report_skipped = True

    def before_import(self, dataset, **kwargs):
        self.created_points = []

    def before_import_row(self, row, **kwargs):
        point_label = (row.get("point_label") or "").strip()
        survey_date = (row.get("survey_date") or "").strip()

        if not point_label:
            raise ValidationError("Missing required column/value: point_label")

        if not survey_date:
            raise ValidationError("Missing required column/value: survey_date")

        if row.get("east") in (None, ""):
            raise ValidationError("Missing required column/value: east")

        if row.get("north") in (None, ""):
            raise ValidationError("Missing required column/value: north")

        if row.get("h") in (None, ""):
            raise ValidationError("Missing required column/value: h")

        point, created = Point.objects.get_or_create(
            label=point_label,
            defaults={
                "active": True,
                "is_fixed": False,
                "notes": "Automatically created during measurement CSV import",
            },
        )

        if created:
            msg = f"Point automatically created from import: label='{point_label}', id={point.pk}"
            self.created_points.append(msg)
            logger.warning(msg)

        try:
            survey = Survey.objects.get(date=survey_date)
        except Survey.DoesNotExist:
            raise ValidationError(f"Survey not found for date='{survey_date}'")
        except Survey.MultipleObjectsReturned:
            raise ValidationError(f"Multiple Surveys found for date='{survey_date}'")

        row["point"] = point.pk
        row["survey"] = survey.pk

        row["notes"] = row.get("notes") or ""
        row["ds_east"] = row.get("ds_east") or None
        row["ds_north"] = row.get("ds_north") or None
        row["ds_h"] = row.get("ds_h") or None
        row["meas_strategy"] = row.get("meas_strategy") or ""
        row["lat"] = row.get("lat") or None
        row["lon"] = row.get("lon") or None
        row["h_orto"] = row.get("h_orto") or None

    def before_save_instance(self, instance, row, **kwargs):
        if instance.east is not None and instance.north is not None:
            instance.geom = GEOSPoint(
                float(instance.east), float(instance.north), srid=32632
            )

    def after_import(self, dataset, result, **kwargs):
        if self.created_points:
            logger.warning(
                "Measurement import completed with %s auto-created points:\n%s",
                len(self.created_points),
                "\n".join(self.created_points),
            )
