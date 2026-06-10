from django.urls import path

from image_index.api_views import CameraListView, ImageListView

urlpatterns = [
    path("cameras/", CameraListView.as_view(), name="api-cameras"),
    path("images/", ImageListView.as_view(), name="api-images"),
]
