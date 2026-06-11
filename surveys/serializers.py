from rest_framework import serializers

from .models import Measurement


class MeasurementSerializer(serializers.ModelSerializer):
    """Measurement with point/survey context.

    Field names match the legacy `points_measurements` view so existing
    consumers (potree, web-map) need no shape changes.
    """

    point_id = serializers.IntegerField(read_only=True)
    survey_id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(source="point.label", read_only=True)
    is_fixed = serializers.BooleanField(source="point.is_fixed", read_only=True)
    survey_date = serializers.DateField(source="survey.date", read_only=True)
    survey_year = serializers.IntegerField(source="survey.year", read_only=True)

    class Meta:
        model = Measurement
        fields = [
            "id",
            "point_id",
            "label",
            "is_fixed",
            "east",
            "north",
            "h",
            "h_orto",
            "lat",
            "lon",
            "survey_id",
            "survey_date",
            "survey_year",
            "meas_date",
            "meas_time",
            "meas_strategy",
            "ds_east",
            "ds_north",
            "ds_h",
        ]
