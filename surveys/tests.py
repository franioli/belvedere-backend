import datetime

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from surveys.models import (
    ActivePoint,
    Measurement,
    Point,
    PointsMeasurement,
    PointsMovementFiltered,
    PointsMovementRaw,
    Survey,
)


class DatabaseViewTests(TestCase):
    """The migration-managed views must exist on a freshly migrated database
    and be queryable through their unmanaged models."""

    VIEW_MODELS = (
        PointsMeasurement,
        PointsMovementRaw,
        PointsMovementFiltered,
        ActivePoint,
    )

    def test_views_exist_and_are_queryable(self):
        for model in self.VIEW_MODELS:
            self.assertEqual(model.objects.count(), 0)


class SurveysApiTests(APITestCase):
    """Tests for /surveys/years/, /surveys/measurements/ and the velocity endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.survey_2015 = Survey.objects.create(
            id=1, date=datetime.date(2015, 7, 20), year=2015
        )
        cls.survey_2016 = Survey.objects.create(
            id=2,
            date=datetime.date(2016, 7, 19),
            year=2016,  # dt = 365 days
        )
        cls.survey_2016b = Survey.objects.create(
            id=3,
            date=datetime.date(2016, 10, 27),
            year=2016,  # dt = 100 days
        )
        cls.empty_survey = Survey.objects.create(
            id=4, date=datetime.date(2020, 7, 1), year=2020
        )
        cls.point = Point.objects.create(id=1, label="D01", is_fixed=False, active=True)
        cls.fixed_point = Point.objects.create(
            id=2, label="FIX1", is_fixed=True, active=True
        )
        # D01 moves by (3, 4, 0) m between 2015 and 2016 -> d = 5 m over 365 days
        cls.m1 = Measurement.objects.create(
            id=1,
            point=cls.point,
            survey=cls.survey_2015,
            east=100.0,
            north=200.0,
            h=50.0,
        )
        cls.m2 = Measurement.objects.create(
            id=2,
            point=cls.point,
            survey=cls.survey_2016,
            east=103.0,
            north=204.0,
            h=50.0,
        )
        # short-gap measurement (dt = 100 days, must be excluded from velocity)
        cls.m3 = Measurement.objects.create(
            id=3,
            point=cls.point,
            survey=cls.survey_2016b,
            east=104.0,
            north=205.0,
            h=50.0,
        )
        cls.m_fixed = Measurement.objects.create(
            id=4,
            point=cls.fixed_point,
            survey=cls.survey_2015,
            east=0.0,
            north=0.0,
            h=0.0,
        )

    def test_years_distinct_sorted_only_with_measurements(self):
        response = self.client.get(reverse("surveys:years"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [2015, 2016])

    def test_measurements_shape_matches_legacy_view(self):
        response = self.client.get(reverse("surveys:measurements"), {"year": 2015})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        record = next(r for r in data if r["label"] == "D01")
        expected_fields = {
            "id", "point_id", "label", "is_fixed", "east", "north", "h",
            "h_orto", "lat", "lon", "survey_id", "survey_date", "survey_year",
            "meas_date", "meas_time", "meas_strategy", "ds_east", "ds_north", "ds_h",
        }  # fmt: skip
        self.assertEqual(set(record), expected_fields)
        self.assertEqual(record["point_id"], 1)
        self.assertEqual(record["survey_year"], 2015)
        self.assertEqual(record["survey_date"], "2015-07-20")
        self.assertEqual(record["east"], 100.0)

    def test_measurements_is_fixed_filter(self):
        response = self.client.get(
            reverse("surveys:measurements"), {"year": 2015, "is_fixed": "false"}
        )
        labels = [r["label"] for r in response.json()]
        self.assertEqual(labels, ["D01"])

    def test_velocity_math_and_dt_window(self):
        response = self.client.get(reverse("surveys:point-velocity", args=["D01"]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # only the 365-day pair survives the 280 < dt < 400 window
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["survey_year"], 2016)
        self.assertEqual(data[0]["survey_date_fin"], "2016-07-19")
        self.assertAlmostEqual(data[0]["v"], 5.0 / 365.0)

    def test_velocity_fixed_point_returns_empty(self):
        response = self.client.get(reverse("surveys:point-velocity", args=["FIX1"]))
        self.assertEqual(response.json(), [])

    def test_velocity_unknown_label_returns_empty(self):
        response = self.client.get(reverse("surveys:point-velocity", args=["NOPE"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
