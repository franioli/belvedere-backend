from django.urls import path

from image_index.views import (
    CameraListView,
    ImageListView,
    image_preview_url,
    image_thumbnail_url,
    serve_image_preview,
    serve_image_thumbnail,
)

app_name = "image_index"

urlpatterns = [
    path(
        "images/<int:pk>/preview/",
        serve_image_preview,
        name="serve_image_preview",
    ),
    path(
        "images/<int:pk>/thumb/",
        serve_image_thumbnail,
        name="serve_image_thumbnail",
    ),
    path("images/<int:pk>/preview-url/", image_preview_url, name="image_preview_url"),
    path("images/<int:pk>/thumb-url/", image_thumbnail_url, name="image_thumbnail_url"),
    path("cameras/", CameraListView.as_view(), name="get-camera-list"),
    path("images/", ImageListView.as_view(), name="get-image-list"),
]
