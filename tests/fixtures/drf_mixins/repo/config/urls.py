from django.urls import path, include
from rest_framework.routers import SimpleRouter
from api.views import Items, status

router = SimpleRouter(trailing_slash=False)
router.register(prefix="items", viewset=Items, basename="item")
urlpatterns = [path("status/", status)] + router.urls
