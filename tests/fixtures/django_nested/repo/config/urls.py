from django.urls import path, include
from api.views import health

urlpatterns = [
    path("health/", health),
    path("api/", include("api.urls")),
    path("v2/", include(("api.urls", "api"), namespace="v2")),
]
