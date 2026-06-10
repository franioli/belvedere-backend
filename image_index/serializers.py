from rest_framework import serializers

from image_index.models import Camera, Image


class CameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = ["id", "slug", "camera_name", "installation_date", "is_active"]


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ["id", "datetime", "filename", "width_px", "height_px", "rotation"]
