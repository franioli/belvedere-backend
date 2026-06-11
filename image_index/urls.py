from django.urls import path

from image_index.views import CameraListView, ImageListView

from .views import serve_image, serve_image_preview, serve_image_thumbnail

app_name = "image_index"

urlpatterns = [
    path(
        "images/<int:pk>/",
        serve_image,
        name="serve_image",
    ),
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
    path("cameras/", CameraListView.as_view(), name="get-camera-list"),
    path("images/", ImageListView.as_view(), name="get-image-list"),
]
