from rest_framework.routers import DefaultRouter
from .views import Users, Reports

router = DefaultRouter()
router.register("users", Users, basename="user")
router.register("reports", Reports, basename="report")
