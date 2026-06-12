"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

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
