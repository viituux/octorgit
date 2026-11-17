from django.urls import path as route, include
from .views import Users

urlpatterns = [route("users/", Users.as_view())]
urlpatterns += [route("internal/", include("api.internal.urls"))]
