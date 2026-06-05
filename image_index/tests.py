from io import BytesIO
from unittest.mock import Mock, patch

from django.test import RequestFactory, TestCase
from PIL import Image as PILImage
from PIL import ImageDraw

from image_index.models import Camera, Image
from image_index.views import serve_image, serve_image_preview, serve_image_thumbnail


class ImageServeViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.camera = Camera.objects.create(
            camera_name="Test camera",
            slug="test-camera",
            s3_bucket="belvedere-images",
            s3_prefix="test/",
        )
        self.image_bytes = self._make_test_image_bytes((2000, 1200))
        self.image = Image.objects.create(
            camera=self.camera,
            bucket="belvedere-images",
            object_key="test/test-image.png",
            filename="test-image.png",
            mime_type="image/png",
        )

    def _make_test_image_bytes(self, size):
        image = PILImage.new("RGB", size)
        draw = ImageDraw.Draw(image)
        for y in range(size[1]):
            color = (y % 256, (y * 3) % 256, (y * 7) % 256)
            draw.line((0, y, size[0], y), fill=color)

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _patch_s3_access(self):
        client = Mock()
        return patch("image_index.views.build_s3_client", return_value=client), patch(
            "image_index.views.get_object_bytes",
            return_value=(self.image_bytes, "image/png"),
        )

    def test_serve_image_returns_original_bytes(self):
        request = self.factory.get("/images/1/serve/")
        build_client_patch, get_bytes_patch = self._patch_s3_access()

        with build_client_patch, get_bytes_patch:
            response = serve_image(request, self.image.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.image_bytes)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_preview_and_thumbnail_are_resized(self):
        request = self.factory.get("/images/1/preview/")
        build_client_patch, get_bytes_patch = self._patch_s3_access()

        with build_client_patch, get_bytes_patch:
            preview_response = serve_image_preview(request, self.image.pk)
            thumbnail_response = serve_image_thumbnail(request, self.image.pk)

        preview_image = PILImage.open(BytesIO(preview_response.content))
        thumbnail_image = PILImage.open(BytesIO(thumbnail_response.content))

        self.assertLessEqual(preview_image.width, 640)
        self.assertLessEqual(preview_image.height, 480)
        self.assertLessEqual(thumbnail_image.width, 160)
        self.assertLessEqual(thumbnail_image.height, 120)
        self.assertLess(len(preview_response.content), len(self.image_bytes))
        self.assertLess(len(thumbnail_response.content), len(self.image_bytes))
