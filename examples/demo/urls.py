from django.urls import path, include
from views import health, UserList

urlpatterns = [
    path("health/", health),
    path("users/", UserList.as_view()),
    path("admin/", include("admin.urls")),
]
