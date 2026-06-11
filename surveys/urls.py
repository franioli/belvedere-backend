from django.urls import path

from .views import MeasurementListView, point_velocity, survey_years

app_name = "surveys"

urlpatterns = [
    path("years/", survey_years, name="years"),
    path("measurements/", MeasurementListView.as_view(), name="measurements"),
    path("points/<str:label>/velocity/", point_velocity, name="point-velocity"),
]
