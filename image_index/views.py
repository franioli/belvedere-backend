import logging
from io import BytesIO

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET
from PIL import Image as PILImage
from PIL import ImageOps
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from image_index.models import Camera, Image
from image_index.s3_utils import (
    build_s3_client,
    generate_presigned_url,
    get_object_bytes,
)
from image_index.serializers import CameraSerializer, ImageSerializer

logger = logging.getLogger("belv")

PREVIEW_SIZE = (1280, 960)
THUMBNAIL_SIZE = (160, 120)
PREVIEW_QUALITY = 80
THUMBNAIL_QUALITY = 60


class ImagePagination(PageNumberPagination):
    page_size = 500
    page_size_query_param = "page_size"
    max_page_size = 1000


class CameraListView(ListAPIView):
    """List cameras. Pass ?active=true to restrict to active cameras only."""

    serializer_class = CameraSerializer

    def get_queryset(self):
        qs = Camera.objects.order_by("camera_name")
        if self.request.query_params.get("active", "").lower() == "true":
            qs = qs.filter(is_active=True)
        return qs


class ImageListView(ListAPIView):
    """List images for a camera, optionally filtered by date range.

    Query params:
        camera: camera slug (required)
        date_after: ISO 8601 datetime lower bound (inclusive)
        date_before: ISO 8601 datetime upper bound (inclusive)
    """

    serializer_class = ImageSerializer
    pagination_class = ImagePagination

    def get_queryset(self):
        qs = Image.objects.order_by("datetime")

        camera_slug = self.request.query_params.get("camera")
        if camera_slug:
            qs = qs.filter(camera__slug=camera_slug)

        date_after = self.request.query_params.get("date_after")
        if date_after:
            qs = qs.filter(datetime__gte=date_after)

        date_before = self.request.query_params.get("date_before")
        if date_before:
            qs = qs.filter(datetime__lte=date_before)

        return qs


def _build_resized_image_response(
    image_bytes: bytes,
    mime_type: str | None,
    max_size: tuple[int, int],
    quality: int = 80,
) -> HttpResponse:
    """Build an in-memory resized image response."""
    with BytesIO(image_bytes) as source:
        with PILImage.open(source) as source_image:
            format_name = (source_image.format or "JPEG").upper()
            image = ImageOps.exif_transpose(source_image)
            image.thumbnail(max_size, PILImage.Resampling.LANCZOS)

            output = BytesIO()
            save_kwargs = {}
            if format_name in {"JPEG", "JPG"}:
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                save_kwargs = {"quality": quality, "optimize": True}
                format_name = "JPEG"
            elif format_name == "WEBP":
                save_kwargs = {"quality": quality, "method": 6}

            image.save(output, format=format_name, **save_kwargs)

    response = HttpResponse(
        output.getvalue(),
        content_type=PILImage.MIME.get(format_name, mime_type or "image/jpeg"),
    )
    response["Cache-Control"] = "private, max-age=86400"
    return response


@require_GET
def serve_image(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve the original image bytes for an image record."""
    image = get_object_or_404(Image, pk=pk)

    try:
        s3 = build_s3_client()
        image_bytes, mime_type = get_object_bytes(s3, image.bucket, image.object_key)
    except Exception as exc:
        logger.exception(f"S3 fetch failed for image pk={pk}")
        raise Http404("Image not available") from exc

    return HttpResponse(
        image_bytes,
        content_type=mime_type or image.mime_type or "application/octet-stream",
    )


@require_GET
def serve_image_preview(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve a preview image or generate one from the source image."""
    image = get_object_or_404(Image, pk=pk)

    try:
        s3 = build_s3_client()
        if image.preview_object_key:
            image_bytes, mime_type = get_object_bytes(
                s3, image.bucket, image.preview_object_key
            )
            response = HttpResponse(image_bytes, content_type=mime_type or "image/jpeg")
            response["Cache-Control"] = "private, max-age=86400"
            return response
        image_bytes, mime_type = get_object_bytes(s3, image.bucket, image.object_key)
    except Exception as exc:
        logger.exception(f"S3 fetch failed for image pk={pk}")
        raise Http404("Image not available") from exc

    return _build_resized_image_response(
        image_bytes,
        mime_type or image.mime_type,
        max_size=PREVIEW_SIZE,
        quality=PREVIEW_QUALITY,
    )


@require_GET
def serve_image_thumbnail(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve a thumbnail or generate one from the source image."""
    image = get_object_or_404(Image, pk=pk)

    try:
        s3 = build_s3_client()
        if image.thumbnail_object_key:
            image_bytes, mime_type = get_object_bytes(
                s3, image.bucket, image.thumbnail_object_key
            )
            response = HttpResponse(image_bytes, content_type=mime_type or "image/jpeg")
            response["Cache-Control"] = "private, max-age=86400"
            return response
        image_bytes, mime_type = get_object_bytes(s3, image.bucket, image.object_key)
    except Exception as exc:
        logger.exception(f"S3 fetch failed for image pk={pk}")
        raise Http404("Image not available") from exc

    return _build_resized_image_response(
        image_bytes,
        mime_type or image.mime_type,
        max_size=THUMBNAIL_SIZE,
        quality=THUMBNAIL_QUALITY,
    )


@require_GET
def image_preview_url(request: HttpRequest, pk: int) -> JsonResponse:
    """Return a presigned S3 URL for the pre-generated preview.

    Falls back to the Django proxy URL if no preview has been generated yet.
    """
    image = get_object_or_404(Image, pk=pk)
    if image.preview_object_key:
        s3 = build_s3_client()
        url = generate_presigned_url(s3, image.bucket, image.preview_object_key)
    else:
        url = request.build_absolute_uri(
            reverse("image_index:serve_image_preview", args=[pk])
        )
    return JsonResponse({"url": url, "expires_in": 900})


@require_GET
def image_thumbnail_url(request: HttpRequest, pk: int) -> JsonResponse:
    """Return a presigned S3 URL for the pre-generated thumbnail.

    Falls back to the Django proxy URL if no thumbnail has been generated yet.
    """
    image = get_object_or_404(Image, pk=pk)
    if image.thumbnail_object_key:
        s3 = build_s3_client()
        url = generate_presigned_url(s3, image.bucket, image.thumbnail_object_key)
    else:
        url = request.build_absolute_uri(
            reverse("image_index:serve_image_thumbnail", args=[pk])
        )
    return JsonResponse({"url": url, "expires_in": 900})
