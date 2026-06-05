from django.urls import path

from .views import serve_image, serve_image_preview, serve_image_thumbnail

app_name = "image_index"

urlpatterns = [
    path("images/<int:pk>/serve/", serve_image, name="serve_image"),
    path("images/<int:pk>/preview/", serve_image_preview, name="serve_image_preview"),
    path(
        "images/<int:pk>/thumbnail/",
        serve_image_thumbnail,
        name="serve_image_thumbnail",
    ),
]
