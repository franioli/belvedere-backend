from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from image_index.models import Camera, Image
from image_index.serializers import CameraSerializer, ImageSerializer


class ImagePagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


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
