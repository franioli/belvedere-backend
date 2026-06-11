import datetime
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import TestCase, override_settings

from surveys.models import Product2D, Product3D, Survey, Volume


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
        self.last_modified = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
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
