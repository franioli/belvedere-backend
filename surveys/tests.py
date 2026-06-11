import datetime
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from surveys.models import (
    ActivePoint,
    Measurement,
    Point,
    PointsMeasurement,
    PointsMovementFiltered,
    PointsMovementRaw,
    Product2D,
    Product3D,
    Survey,
    Volume,
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


class ProductModelTests(TestCase):
    def setUp(self):
        self.survey = Survey.objects.create(
            id=1, date=datetime.date(1977, 9, 1), year=1977
        )

    @override_settings(S3_ENDPOINT_URL="https://s3.example.com")
    def test_file_path_built_from_bucket_and_key(self):
        product = Product2D.objects.create(
            survey=self.survey,
            data_type="ortofoto",
            bucket="belvedere-products",
            object_key="products_2d/1977/orto 50cm.tif",
        )
        self.assertEqual(
            product.file_path,
            "https://s3.example.com/belvedere-products/products_2d/1977/orto%2050cm.tif",
        )

    def test_file_path_empty_until_uploaded(self):
        product = Product3D.objects.create(survey=self.survey, data_type="pointcloud")
        self.assertEqual(product.file_path, "")

    def test_survey_with_products_is_protected(self):
        Product2D.objects.create(survey=self.survey, data_type="dsm")
        with self.assertRaises(ProtectedError):
            self.survey.delete()

    def test_volume_relations(self):
        survey2 = Survey.objects.create(id=2, date=datetime.date(1991, 9, 1), year=1991)
        volume = Volume.objects.create(
            survey=survey2, survey_prev=self.survey, dv=-1000.0, density=850
        )
        self.assertEqual(self.survey.volumes_as_previous.get(), volume)
        self.assertEqual(survey2.volumes.get(), volume)


class IndexS3ProductsCommandTests(TestCase):
    def setUp(self):
        self.survey = Survey.objects.create(
            id=1, date=datetime.date(1977, 9, 1), year=1977
        )
        self.product = Product2D.objects.create(
            survey=self.survey,
            data_type="ortofoto",
            object_key="products_2d/1977/orto.tif",
        )
        self.last_modified = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)
        self.s3 = Mock()
        paginator = Mock()
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "products_2d/1977/orto.tif",
                        "ETag": '"abc123"',
                        "Size": 42,
                        "LastModified": self.last_modified,
                    },
                    {"Key": "orphan/file.laz", "ETag": '"zzz"', "Size": 1},
                ]
            }
        ]
        self.s3.get_paginator.return_value = paginator

    def _call(self, *args: str) -> str:
        out = StringIO()
        with patch(
            "surveys.management.commands.index_s3_products.build_s3_client",
            return_value=self.s3,
        ):
            call_command(
                "index_s3_products", "--bucket", "test-bucket", *args, stdout=out
            )
        return out.getvalue()

    def test_syncs_matching_product_and_reports_orphans(self):
        output = self._call()
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_uploaded)
        self.assertEqual(self.product.bucket, "test-bucket")
        self.assertEqual(self.product.s3_etag, "abc123")
        self.assertEqual(self.product.file_size_bytes, 42)
        self.assertEqual(self.product.s3_last_modified, self.last_modified)
        self.assertIn("orphan/file.laz", output)

    def test_dry_run_does_not_write(self):
        output = self._call("--dry-run")
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_uploaded)
        self.assertIsNone(self.product.bucket)
        self.assertIn("dry-run", output)
