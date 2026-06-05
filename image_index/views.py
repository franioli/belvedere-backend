from io import BytesIO

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from PIL import Image as PILImage
from PIL import ImageOps

from image_index.models import Image
from image_index.s3_utils import build_s3_client, get_object_bytes


def _build_resized_image_response(image_bytes, mime_type, max_size, quality=80):
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
def serve_image(request, pk):
    image = get_object_or_404(Image, pk=pk)

    try:
        s3 = build_s3_client()
        image_bytes, mime_type = get_object_bytes(s3, image.bucket, image.object_key)
    except Exception as exc:
        raise Http404(f"Unable to load image: {exc}") from exc

    return HttpResponse(
        image_bytes,
        content_type=mime_type or image.mime_type or "application/octet-stream",
    )


@require_GET
def serve_image_thumbnail(request, pk):
    image = get_object_or_404(Image, pk=pk)

    try:
        s3 = build_s3_client()
        image_bytes, mime_type = get_object_bytes(s3, image.bucket, image.object_key)
    except Exception as exc:
        raise Http404(f"Unable to load image: {exc}") from exc

    return _build_resized_image_response(
        image_bytes,
        mime_type or image.mime_type,
        max_size=(160, 120),
        quality=72,
    )


@require_GET
def serve_image_preview(request, pk):
    image = get_object_or_404(Image, pk=pk)

    try:
        s3 = build_s3_client()
        image_bytes, mime_type = get_object_bytes(s3, image.bucket, image.object_key)
    except Exception as exc:
        raise Http404(f"Unable to load image: {exc}") from exc

    return _build_resized_image_response(
        image_bytes,
        mime_type or image.mime_type,
        max_size=(640, 480),
        quality=80,
    )
